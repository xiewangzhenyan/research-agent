"""Real PostgreSQL lifecycle, extraction fences, semantic scope and consent tests."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import func, select

from app.db.models.conversation import Message
from app.db.models.memory import MemoryExtractionJob, MemoryItem, MemoryProposal, MemoryVersion
from app.db.session import get_worker_db_context
from app.schemas.memory import ExtractionResult
from app.services import memory_extraction as extraction
from app.services.agent import persist_user_turn
from app.worker import memory as worker
from tests.test_project_spaces_integration import header, workspace

pytestmark = pytest.mark.skipif(os.getenv("RUN_TASK_DB_TESTS") != "1", reason="disposable DB only")
BASE = "/api/v1/memory"
TEXT = "请记住，本项目的超表面测量温度固定为 30°C，不允许使用 25°C。"
NOTE = {"title": "测量要求", "content": "本项目超表面测量温度固定为 25°C。", "kind": "constraint"}


async def enable(client, project, **extra):
    h = header(project)
    revision = (await client.get(BASE, headers=h)).json()["revision"]
    r = await client.put(
        BASE + "/settings",
        headers=h,
        json={"enabled": True, "auto_extract": True, "revision": revision, **extra},
    )
    assert r.status_code == 200, r.text


async def message(client, project, text=TEXT):
    h = header(project)
    cid = (await client.post("/api/v1/conversations", headers=h, json={})).json()["id"]
    r = await client.post(
        f"/api/v1/conversations/{cid}/messages", headers=h, json={"content": text}
    )
    assert r.status_code == 201, r.text
    return UUID(r.json()["id"]), cid


async def queue(owner, project, mid):
    async with get_worker_db_context() as db:
        source = await db.get(Message, mid)
        await extraction.enqueue(db, owner, project.id if project else None, source)
        return await db.scalar(
            select(MemoryExtractionJob.id).where(MemoryExtractionJob.source_message_id == mid)
        )


def result(action="add", target=None):
    return ExtractionResult.model_validate(
        {
            "memories": [
                {
                    "title": "测量温度",
                    "content": TEXT,
                    "kind": "constraint",
                    "action": action,
                    "target": target,
                    "reason": "用户明确指定新的测量温度",
                    "quote": TEXT,
                }
            ]
        }
    )


async def run(job, output=None):
    with patch.object(
        extraction,
        "infer",
        AsyncMock(
            return_value=(
                output or result(),
                {"requests": 1, "input_tokens": 50, "output_tokens": 40},
            )
        ),
    ):
        await worker.locked(7301, job, worker.execute)


def test_expiry_archive_versions_and_conflicting_revision():
    async def check():
        async with workspace() as (_, _, _, _, a, b, _, client):
            h = header(a)
            await enable(client, a, semantic_recall=False)
            expired = (
                await client.post(
                    BASE,
                    headers=h,
                    json={
                        **NOTE,
                        "expires_on": str(datetime.now(UTC).date() - timedelta(days=1)),
                        "pinned": True,
                    },
                )
            ).json()
            assert expired["state"] == "expired"
            assert (await client.post(BASE + "/preview", headers=h, json={"query": "测量"})).json()[
                "items"
            ] == []
            url = BASE + "/" + expired["id"]
            active = (
                await client.put(
                    url,
                    headers=h,
                    json={
                        **NOTE,
                        "revision": 1,
                        "expires_on": str(datetime.now(UTC).date()),
                        "pinned": True,
                    },
                )
            ).json()
            assert active["state"] == "active"
            assert (
                len(
                    (
                        await client.post(BASE + "/preview", headers=h, json={"query": "测量"})
                    ).json()["items"]
                )
                == 1
            )
            archived = await client.post(url + "/archive", headers=h, json={"revision": 2})
            assert archived.json()["state"] == "archived"
            assert (await client.post(BASE + "/preview", headers=h, json={"query": "测量"})).json()[
                "items"
            ] == []
            assert (
                await client.post(url + "/restore", headers=h, json={"revision": 2})
            ).status_code == 409
            assert (
                await client.post(url + "/restore", headers=header(b), json={"revision": 3})
            ).status_code == 404
            assert (await client.post(url + "/restore", headers=h, json={"revision": 3})).json()[
                "state"
            ] == "active"
            for rev in range(4, 34):
                assert (
                    await client.put(
                        url, headers=h, json={**NOTE, "content": f"测量版本 {rev}", "revision": rev}
                    )
                ).status_code == 200
            history = (await client.get(url + "/history", headers=h)).json()["items"]
            assert (
                len(history) == 30 and history[0]["revision"] == 34 and history[-1]["revision"] == 5
            )
            assert (await client.get(url + "/history", headers=header(b))).status_code == 404

    asyncio.run(check())


def test_proposals_review_update_source_history_and_idempotent_delivery():
    async def check():
        async with workspace() as (owner, other, _, _, a, b, _, client):
            h = header(a)
            await enable(client, a, semantic_recall=False)
            old_mid, old_cid = await message(client, a, NOTE["content"])
            note = (
                await client.post(BASE, headers=h, json={**NOTE, "source_message_id": str(old_mid)})
            ).json()
            new_mid, new_cid = await message(client, a)
            job = await queue(owner, a, new_mid)
            assert await queue(owner, a, new_mid) == job
            await asyncio.gather(run(job, result("update", 0)), run(job, result("update", 0)))
            data = (await client.get(BASE, headers=h)).json()
            assert len(data["proposals"]) == 1
            assert data["items"][0]["content"] == NOTE["content"]
            p = data["proposals"][0]
            assert p["target"]["id"] == note["id"]
            body = {**p["payload"], "revision": p["revision"], "content": TEXT + " 已核对。"}
            url = BASE + f"/proposals/{p['id']}/accept"
            assert (await client.post(url, headers=header(b), json=body)).status_code == 404
            denied = await client.post(
                url, headers=h, json={**body, "source_message_id": str(old_mid)}
            )
            assert denied.status_code == 400
            accepted = await client.post(url, headers=h, json=body)
            assert accepted.status_code == 200, accepted.text
            assert accepted.json()["item"]["revision"] == 2
            assert (await client.post(url, headers=h, json=body)).status_code == 409
            assert (await client.get(BASE, headers=h)).json()["proposals"] == []
            assert (
                len((await client.get(BASE + f"/{note['id']}/history", headers=h)).json()["items"])
                == 2
            )
            await client.delete(f"/api/v1/conversations/{old_cid}", headers=h)
            # Current source was deliberately replaced by the reviewed update.
            assert len((await client.get(BASE, headers=h)).json()["items"]) == 1
            assert (
                len((await client.get(BASE + f"/{note['id']}/history", headers=h)).json()["items"])
                == 1
            )
            await client.delete(f"/api/v1/conversations/{new_cid}", headers=h)
            assert (await client.get(BASE, headers=h)).json()["items"] == []
            async with get_worker_db_context() as db:
                assert await db.scalar(select(func.count()).select_from(MemoryVersion)) == 0

    asyncio.run(check())


@pytest.mark.parametrize("change", ["settings", "source", "target"])
def test_changes_during_inference_never_write_stale_suggestions(change):
    async def check():
        async with workspace() as (owner, _, _, _, a, _, _, client):
            h = header(a)
            await enable(client, a)
            note = (await client.post(BASE, headers=h, json=NOTE)).json()
            mid, cid = await message(client, a)
            job = await queue(owner, a, mid)

            async def infer(*args):
                if change == "settings":
                    await enable(client, a, enabled=False)
                    await enable(client, a)  # Off -> on must not revive the old settings revision.
                elif change == "source":
                    await client.delete(f"/api/v1/conversations/{cid}", headers=h)
                else:
                    await client.put(
                        BASE + "/" + note["id"],
                        headers=h,
                        json={**NOTE, "content": "已改为 35°C", "revision": 1},
                    )
                return result("update", 0), {}

            with patch.object(extraction, "infer", infer):
                await worker.locked(7301, job, worker.execute)
            assert (await client.get(BASE, headers=h)).json()["proposals"] == []

    asyncio.run(check())


def test_reject_stale_accept_expired_proposal_and_retry_bounds():
    async def check():
        async with workspace() as (owner, _, _, _, a, _, _, client):
            h = header(a)
            await enable(client, a)
            note = (await client.post(BASE, headers=h, json=NOTE)).json()
            mid, _ = await message(client, a)
            job = await queue(owner, a, mid)
            await run(job, result("update", 0))
            p = (await client.get(BASE, headers=h)).json()["proposals"][0]
            await client.put(
                BASE + "/" + note["id"],
                headers=h,
                json={**NOTE, "content": "测量改为 40°C", "revision": 1},
            )
            url = BASE + f"/proposals/{p['id']}"
            assert (
                await client.post(url + "/accept", headers=h, json={**p["payload"], "revision": 1})
            ).status_code == 409
            assert (
                await client.post(url + "/reject", headers=h, json={"revision": 1})
            ).status_code == 200
            assert (
                await client.post(url + "/reject", headers=h, json={"revision": 1})
            ).status_code == 409
            mid, _ = await message(client, a)
            failed = await queue(owner, a, mid)
            with patch.object(
                extraction, "infer", AsyncMock(side_effect=RuntimeError("private provider payload"))
            ):
                await worker.locked(7301, failed, worker.execute)
                retry = BASE + f"/jobs/{failed}/retry"
                assert (await client.post(retry, headers=h)).status_code == 200
                await worker.locked(7301, failed, worker.execute)
                assert (await client.post(retry, headers=h)).status_code == 409
            data = (await client.get(BASE, headers=h)).json()
            assert "private provider payload" not in str(data)
            assert next(j for j in data["jobs"] if j["id"] == str(failed))["attempts"] == 2
            async with get_worker_db_context() as db:
                proposal = await db.get(MemoryProposal, UUID(p["id"]))
                proposal.status, proposal.revision = "pending", 1
                proposal.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            assert (
                await client.post(url + "/accept", headers=h, json={**p["payload"], "revision": 1})
            ).status_code == 409
            assert (await client.get(BASE, headers=h)).json()["proposals"] == []

    asyncio.run(check())


def test_actual_pydantic_extraction_and_persisted_chat_queue_hook():
    async def check():
        async with workspace() as (owner, _, _, _, a, _, user, client):
            await enable(client, a)
            await client.put(
                f"/api/v1/projects/{a.id}", json={"name": a.name, "knowledge_base_ids": []}
            )
            with patch("app.services.agent.get_db_context", get_worker_db_context):
                cid, _, _ = await persist_user_turn(
                    user, TEXT, [], None, None, {"active_knowledge_base_ids": []}, a.id
                )
            async with get_worker_db_context() as db:
                job = await db.scalar(
                    select(MemoryExtractionJob).where(MemoryExtractionJob.user_id == owner)
                )
                source = await db.get(Message, job.source_message_id)
                assert str(source.conversation_id) == cid and source.content == TEXT

            def model(messages, info):
                assert TEXT in str(messages)
                return ModelResponse(
                    parts=[
                        ToolCallPart(info.output_tools[0].name, result().model_dump(mode="json"))
                    ]
                )

            with patch.object(extraction, "_build_model", return_value=FunctionModel(model)):
                await worker.locked(7301, job.id, worker.execute)
            data = (await client.get(BASE, headers=header(a))).json()
            assert len(data["proposals"]) == 1 and data["jobs"][0]["usage"]["requests"] == 1
            # Restore a KB default and check the native strict-mode snapshot.
            await client.put(
                f"/api/v1/projects/{a.id}",
                json={"name": a.name, "knowledge_base_ids": a.knowledge_base_ids},
            )
            with patch("app.services.agent.get_db_context", get_worker_db_context):
                await persist_user_turn(user, TEXT, [], None, None, None, a.id)
            async with get_worker_db_context() as db:
                assert (
                    len(
                        list(
                            await db.scalars(
                                select(MemoryExtractionJob).where(
                                    MemoryExtractionJob.user_id == owner
                                )
                            )
                        )
                    )
                    == 1
                )

    asyncio.run(check())


def test_semantic_scope_revision_expiry_and_keyword_fallback():
    async def check():
        async with workspace() as (owner, _, _, _, a, b, _, client):
            for project in (a, b, None):
                await enable(client, project)
                await client.post(BASE, headers=header(project), json=NOTE)
            vector = [1.0] + [0.0] * 511
            async with get_worker_db_context() as db:
                for item in await db.scalars(select(MemoryItem).where(MemoryItem.user_id == owner)):
                    item.embedding, item.embedding_revision, item.embedding_model = (
                        vector,
                        1,
                        "review-fingerprint",
                    )
            with patch(
                "app.services.memory_semantic.query_vector",
                AsyncMock(return_value=(vector, "review-fingerprint")),
            ):
                preview = (
                    await client.post(
                        BASE + "/preview", headers=header(a), json={"query": "unrelated synonym"}
                    )
                ).json()
                assert preview["retrieval_mode"] == "hybrid" and len(preview["items"]) == 1
                item_id = preview["items"][0]["id"]
                await client.post(
                    BASE + f"/{item_id}/archive", headers=header(a), json={"revision": 1}
                )
                assert (
                    await client.post(
                        BASE + "/preview", headers=header(a), json={"query": "超表面"}
                    )
                ).json()["items"] == []
            with patch(
                "app.services.memory_semantic.query_vector", AsyncMock(side_effect=TimeoutError)
            ):
                preview = (
                    await client.post(
                        BASE + "/preview", headers=header(b), json={"query": "超表面"}
                    )
                ).json()
                assert (
                    preview["retrieval_mode"] == "keyword"
                    and preview["semantic_status"] == "unavailable"
                )
                assert len(preview["items"]) == 1
            async with get_worker_db_context() as db:
                item = await db.get(MemoryItem, UUID(item_id))
                item.archived_at = None
                item.embedding_revision = 1  # Current revision is 2: stale vectors never match.
            with patch(
                "app.services.memory_semantic.query_vector",
                AsyncMock(return_value=(vector, "review-fingerprint")),
            ):
                assert (
                    await client.post(
                        BASE + "/preview", headers=header(a), json={"query": "unrelated synonym"}
                    )
                ).json()["items"] == []

    asyncio.run(check())


def test_queue_quotas_and_running_job_restart():
    async def check():
        async with workspace() as (owner, _, _, _, a, _, _, client):
            await enable(client, a)
            jobs = []
            for _ in range(11):
                mid, _ = await message(client, a)
                jobs.append(await queue(owner, a, mid))
            assert all(jobs[:10]) and jobs[10] is None
            async with get_worker_db_context() as db:
                job = await db.get(MemoryExtractionJob, jobs[0])
                job.status, job.attempts = "running", 1
            await run(jobs[0])
            async with get_worker_db_context() as db:
                job = await db.get(MemoryExtractionJob, jobs[0])
                assert job.status == "completed" and job.attempts == 2

    asyncio.run(check())


@pytest.mark.parametrize("change", ["content", "settings"])
def test_index_never_saves_a_vector_after_the_note_or_consent_changes(change):
    async def check():
        async with workspace() as (owner, _, _, _, a, _, _, client):
            h = header(a)
            await enable(client, a)
            note = (await client.post(BASE, headers=h, json=NOTE)).json()

            async def check_connection():
                if change == "content":
                    await client.put(
                        BASE + "/" + note["id"],
                        headers=h,
                        json={**NOTE, "content": "新的约束内容", "revision": 1},
                    )
                else:
                    await enable(client, a, enabled=False)

            with patch(
                "app.services.memory_semantic.encode_note",
                return_value=([1.0] + [0.0] * 511, "review-model"),
            ):
                await worker.index(UUID(note["id"]), check_connection)
            async with get_worker_db_context() as db:
                item = await db.get(MemoryItem, UUID(note["id"]))
                assert item.embedding is None and item.embedding_revision is None

    asyncio.run(check())


def test_assistant_sources_are_not_extracted_and_daily_quota_is_account_wide():
    async def check():
        async with workspace() as (owner, _, _, _, a, b, _, client):
            await enable(client, a)
            await enable(client, b)
            mid, _ = await message(client, a)
            async with get_worker_db_context() as db:
                msg = await db.get(Message, mid)
                msg.role = "assistant"
            assert await queue(owner, a, mid) is None
            for _ in range(20):
                mid, _ = await message(client, a)
                job_id = await queue(owner, a, mid)
                assert job_id is not None
                async with get_worker_db_context() as db:
                    job = await db.get(MemoryExtractionJob, job_id)
                    worker.finish(job, "completed")
            mid, _ = await message(client, b)
            assert await queue(owner, b, mid) is None

    asyncio.run(check())


@pytest.mark.skipif(
    os.getenv("RUN_LOCAL_MEMORY_MODEL") != "1", reason="requires mounted offline model"
)
def test_real_offline_vector_index_and_recall_without_embedding_api():
    async def check():
        async with workspace() as (owner, _, _, _, a, _, _, client):
            h = header(a)
            await enable(client, a)
            note = (await client.post(BASE, headers=h, json=NOTE)).json()
            await worker.locked(7302, UUID(note["id"]), worker.index)
            async with get_worker_db_context() as db:
                indexed = await db.get(MemoryItem, UUID(note["id"]))
                assert len(indexed.embedding) == 512 and indexed.embedding_revision == 1
                assert indexed.embedding_model.startswith("memory-mean320-v1:")
            response = await client.post(
                BASE + "/preview", headers=h, json={"query": "超表面测量的温度控制要求是什么？"}
            )
            assert response.status_code == 200, response.text
            assert response.json()["retrieval_mode"] == "hybrid", response.text
            assert [i["id"] for i in response.json()["items"]] == [note["id"]]

    asyncio.run(check())


def test_dispatcher_handles_default_project_index_and_candidate_job():
    async def check():
        async with workspace() as (owner, _, _, _, _, _, _, client):
            await enable(client, None)
            note = (await client.post(BASE, json=NOTE)).json()
            mid, _ = await message(client, None)
            job_id = await queue(owner, None, mid)
            with (
                patch.object(extraction, "infer", AsyncMock(return_value=(result(), {}))),
                patch(
                    "app.services.memory_semantic.encode_note",
                    return_value=([1.0] + [0.0] * 511, "review"),
                ),
            ):
                await worker.cycle()
            async with get_worker_db_context() as db:
                assert (await db.get(MemoryExtractionJob, job_id)).status == "completed"
                assert (await db.get(MemoryItem, UUID(note["id"]))).embedding_revision == 1

    asyncio.run(check())
