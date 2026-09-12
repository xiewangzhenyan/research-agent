"""Live authored-source checks; review creates isolated users, release accepts explicit fixtures."""

import argparse
import asyncio
import json
import secrets
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import httpx
import websockets
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.db.models.knowledge import KnowledgeDocument
from app.db.models.user import User
from app.db.session import get_db_context
from app.schemas.knowledge_entry import ManualCreate, ManualUpdate
from app.services.knowledge_entries import KnowledgeEntryService
from app.worker.tasks.knowledge import process_document


async def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--fixtures", type=Path)
    args = parser.parse_args()
    path = args.fixtures or Path("/tmp/authored-fixtures.json")
    if args.fixtures:
        users = json.loads(path.read_text())
    else:
        assert settings.POSTGRES_DB.endswith("_review")
        users = []
        async with get_db_context() as db:
            for i in range(2):
                password = secrets.token_urlsafe(24)
                user = User(
                    email=f"authored-check-{int(time.time())}-{i}@example.com",
                    full_name="资料验收",
                    hashed_password=get_password_hash(password),
                    onboarding_completed_at=datetime.now(UTC),
                )
                db.add(user)
                await db.flush()
                users.append({"id": str(user.id), "email": user.email, "password": password})
    for user in users:
        user["token"] = create_access_token(user["id"])

    def checkpoint():
        path.write_text(json.dumps(users))
        path.chmod(0o600)

    checkpoint()
    a, b = users
    async with httpx.AsyncClient(
        base_url="http://localhost:38001/api/v1/knowledge", timeout=60
    ) as client:

        async def req(method, url, user=a, **kw):
            return await client.request(
                method, url, headers={"Authorization": "Bearer " + user["token"]}, **kw
            )

        async def ready(kb):
            for _ in range(180):
                rows = (await req("GET", f"/bases/{kb}/documents")).json()
                if rows and all(d["status"] == "ready" for d in rows):
                    return rows
                assert not any(d["status"] == "failed" for d in rows), rows
                await asyncio.sleep(0.5)
            raise AssertionError("Index timeout")

        kb = (await req("POST", "/bases", json={"name": "手动知识与FAQ验收"})).json()["id"]
        a["base_id"] = kb
        checkpoint()
        response = await req(
            "POST",
            f"/bases/{kb}/documents",
            files={"file": ("handbook.txt", "普通上传文件仍使用本地索引。".encode())},
        )
        assert response.status_code == 201, response.text
        fid = response.json()["id"]
        before = await ready(kb)
        if not args.fixtures:
            # Only review: existing files survive schema downgrade/upgrade before authoring begins.
            for revision in ["0034_retrieval_preferences", "head"]:
                command = "downgrade" if revision != "head" else "upgrade"
                subprocess.run(["alembic", command, revision], check=True, capture_output=True)
            after = await ready(kb)
            assert after == before, (before, after)
            print(
                "Migration round-trip preserves an indexed upload and assigns file/revision defaults: PASS",
                flush=True,
            )
        assert (await req("GET", f"/documents/{fid}/entry")).status_code == 400
        manual = {
            "kind": "manual",
            "title": "设备使用规范",
            "content": "启动设备前检查接地和电源连接。使用完毕先停止运行,再切断电源。",
        }
        response = await req("POST", f"/bases/{kb}/entries", json=manual)
        assert response.status_code == 201, response.text
        a["manual_id"] = response.json()["id"]
        faq = {
            "kind": "faq",
            "question": "青岚计划住宿报销的上限是多少?",
            "answer": "每人每晚住宿报销上限为620元,申请时需提交有效发票。",
        }
        response = await req("POST", f"/bases/{kb}/entries", json=faq)
        assert response.status_code == 201 and response.json()["status"] == "pending", response.text
        did = response.json()["id"]
        a["document_id"] = did
        checkpoint()
        assert (await req("POST", f"/bases/{kb}/entries", json=faq)).status_code == 409
        assert (await req("POST", f"/bases/{kb}/entries", json=faq, user=b)).status_code == 404
        assert (
            await req("PUT", f"/documents/{fid}/entry", json=faq | {"revision": 1})
        ).status_code == 400
        await ready(kb)
        for method, suffix, payload in [
            ("GET", "entry", {}),
            ("PUT", "entry", {"json": faq | {"revision": 1}}),
            ("GET", "download", {}),
        ]:
            assert (
                await req(method, f"/documents/{did}/{suffix}", user=b, **payload)
            ).status_code == 404
        loaded = (await req("GET", f"/documents/{did}/entry")).json()
        assert loaded["entry"] == faq and loaded["revision"] == 1
        config = {"mode": "keyword", "result_limit": 3}
        assert (await req("PUT", "/retrieval-config", json=config)).status_code == 200
        search = {
            "knowledge_base_ids": [kb],
            "document_ids": [did],
            "query": "青岚计划住宿",
            "diagnostics": True,
        }
        result = (await req("POST", "/search", json=search)).json()
        assert result["items"][0]["source_kind"] == "faq" and "620" in result["items"][0]["content"]
        assert result["items"][0]["page"] is None
        assert (await req("POST", "/search", json=search, user=b)).status_code == 404
        print(
            "Real file/manual/FAQ indexing; structured edit and export; duplicate prevention; account-scoped reads, writes and search: PASS",
            flush=True,
        )

        captured = {}
        async with websockets.connect(
            "ws://localhost:38001/api/v1/ws/agent",
            subprotocols=["access_token." + a["token"], "chat"],
        ) as ws:
            await ws.send(
                json.dumps(
                    {
                        "message": faq["question"],
                        "knowledge_base_ids": [kb],
                        "knowledge_document_ids": [did],
                    }
                )
            )
            async with asyncio.timeout(150):
                while True:
                    event = json.loads(await ws.recv())
                    kind, data = event["type"], event["data"]
                    assert kind != "error", data
                    if kind == "conversation_created":
                        captured["conversation_id"] = data["conversation_id"]
                    elif kind == "tool_result":
                        captured["retrieval"] = json.loads(data["content"])
                    elif kind == "final_result":
                        captured["answer"] = data["output"]
                    elif kind == "complete":
                        break
        assert "620" in captured["answer"], captured
        sid = captured["retrieval"]["items"][0]["citation_id"]
        citation = (await req("GET", f"/citations/{sid}")).json()
        assert (
            citation["source_kind"] == "faq" and citation["quotes"] and citation["page"] is None
        ), citation
        assert all(q in citation["content"] for q in citation["quotes"])
        assert (await req("GET", f"/citations/{sid}", user=b)).status_code == 404
        new_faq = faq | {"answer": "每人每晚住宿报销上限调整为720元,申请时需提交有效发票。"}
        edited = await req("PUT", f"/documents/{did}/entry", json=new_faq | {"revision": 1})
        assert edited.status_code == 200 and edited.json()["revision"] == 2, edited.text
        conflict = await req("PUT", f"/documents/{did}/entry", json=faq | {"revision": 1})
        assert (
            conflict.status_code == 409 and conflict.json()["error"]["code"] == "REVISION_CONFLICT"
        )
        assert (await req("PUT", f"/documents/{did}/entry", json=new_faq | {"revision": 2})).json()[
            "revision"
        ] == 2
        await ready(kb)
        revised = (await req("POST", "/search", json=search)).json()
        assert (
            all("620" not in s["content"] for s in revised["items"])
            and "720" in revised["items"][0]["content"]
        )
        assert revised["items"][0]["index_generation"] != result["items"][0]["index_generation"]
        retained = (await req("GET", f"/citations/{sid}")).json()
        assert retained["state"] == "reindexed" and retained["content"] == citation["content"]
        assert "720" in (await req("GET", f"/documents/{did}/download")).text
        print(
            "Generated FAQ answer has literal citation; revision conflict cannot overwrite; current search updates while historical quote remains: PASS",
            flush=True,
        )

        if not args.fixtures:
            # Real DB + actual processing routine: edits invalidate a worker already computing vectors.
            async with get_db_context() as db:
                guard = await KnowledgeEntryService(db, UUID(a["id"])).create_entry(
                    UUID(kb),
                    ManualCreate(
                        kind="manual", title="处理中编辑验收", content="旧版本只有数字111。"
                    ),
                )
                guard_id = guard.id
            started, release = threading.Event(), threading.Event()
            from app.worker.tasks import knowledge as tasks

            real_embed = tasks.embed

            def blocked_embed(texts):
                started.set()
                assert release.wait(20)
                return real_embed(texts)

            with patch.object(tasks, "embed", blocked_embed):
                old = asyncio.create_task(process_document(guard_id))
                try:
                    assert await asyncio.to_thread(started.wait, 15)
                    async with get_db_context() as db:
                        changed = await KnowledgeEntryService(db, UUID(a["id"])).update_entry(
                            guard_id,
                            ManualUpdate(
                                kind="manual",
                                title="处理中编辑验收",
                                content="新版本只有数字222。",
                                revision=1,
                            ),
                        )
                        new_job = changed.job_id
                finally:
                    release.set()
                    await old
            async with get_db_context() as db:
                row = await db.scalar(
                    select(KnowledgeDocument).where(KnowledgeDocument.id == guard_id)
                )
                assert row.status == "pending" and row.job_id == new_job and row.chunk_count == 0
            await process_document(guard_id)
            guard_search = (
                await req(
                    "POST",
                    "/search",
                    json={
                        "knowledge_base_ids": [kb],
                        "document_ids": [str(guard_id)],
                        "query": "222",
                    },
                )
            ).json()
            assert (
                "222" in guard_search["items"][0]["content"]
                and "111" not in guard_search["items"][0]["content"]
            )
            assert (await req("DELETE", f"/documents/{guard_id}")).status_code == 204
            forbidden = subprocess.run(
                ["alembic", "downgrade", "0034_retrieval_preferences"], capture_output=True
            )
            assert (
                forbidden.returncode != 0
                and b"Cannot downgrade while authored knowledge exists" in forbidden.stderr
            )
            print(
                "Edit during vector generation blocks stale publication; new source indexes; unsafe schema downgrade refuses to discard authored data: PASS",
                flush=True,
            )
        assert (await req("DELETE", f"/documents/{did}", user=b)).status_code == 404
        assert (await req("DELETE", f"/documents/{did}")).status_code == 204
        assert (await req("GET", f"/citations/{sid}")).json() == {
            "state": "deleted",
            "title": "原文已删除",
            "content": "",
        }
        assert (await req("GET", f"/documents/{did}/entry")).status_code == 404
        recreated = (await req("POST", f"/bases/{kb}/entries", json=new_faq)).json()
        a.update(
            document_id=recreated["id"],
            citation_id=sid,
            conversation_id=captured["conversation_id"],
        )
        checkpoint()
        await ready(kb)
        print(
            "Deleting a FAQ removes editable source/index and erases historical source content without filesystem errors: PASS",
            flush=True,
        )


if __name__ == "__main__":
    asyncio.run(main())
