"""Opt-in PostgreSQL tests: source fidelity, isolation, durable indexing and edits."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, update

from app.core.exceptions import BadRequestError, NotFoundError
from app.db.models.agent_run import AgentRun
from app.db.models.conversation import Conversation, Message
from app.db.models.conversation_context import ConversationContextBlock as Block
from app.db.models.conversation_context import ConversationContextJob as Job
from app.db.models.memory import MemoryItem
from app.db.session import get_worker_db_context
from app.schemas.model_config import EffectiveAnswerConfig
from app.services import conversation_context as context
from app.services.model_config import resolve_generation_config
from app.worker import conversation_context as worker
from tests.test_project_spaces_integration import header, workspace

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_TASK_DB_TESTS") != "1", reason="disposable database only"
)


async def transcript(owner, project=None, count=24):
    async with get_worker_db_context() as db:
        conversation = Conversation(user_id=owner, project_id=project)
        db.add(conversation)
        await db.flush()
        start = datetime.now(UTC) - timedelta(hours=1)
        messages = []
        for i in range(count):
            text = (
                "做饭不要放花生，过敏；预算三十元。"
                if i == 0
                else "建议清蒸鱼，未使用花生。"
                if i == 1
                else f"数学定积分讨论第{i}题"
                if i < 12
                else f"经济市场研究第{i}条"
            )
            messages.append(
                Message(
                    conversation_id=conversation.id,
                    role="user" if i % 2 == 0 else "assistant",
                    content=text,
                    created_at=start + timedelta(seconds=i),
                )
            )
        source = Message(
            conversation_id=conversation.id,
            role="user",
            content="回到做饭，刚才有哪些限制？",
            created_at=start + timedelta(seconds=count),
        )
        messages.append(source)
        db.add_all(messages)
        await db.flush()
        request = {
            "conversation_id": str(conversation.id),
            "user_message_id": str(source.id),
            "prompt": source.content,
            "knowledge_base_ids": [],
            "knowledge_strict": False,
            "file_ids": [],
        }
    return conversation.id, messages, request


async def prepare(request, owner, project=None):
    async with get_worker_db_context() as db:
        return await context.recall(db, request, owner, project, resolve_generation_config({}))


async def index(cid, hook=None):
    original = worker.summarize

    async def extract(data, config, allow):
        if hook:
            await hook()
        return await original(data, config, False)

    with (
        patch.object(worker, "summarize", extract),
        patch.object(worker, "encode_note", side_effect=RuntimeError("offline")),
    ):
        await worker.execute(cid, AsyncMock())


def test_a_b_c_a_recovers_original_constraints_without_crossing_any_scope():
    async def check():
        async with workspace() as (owner, other, kb, foreign, a, b, user, client):
            cid, messages, request = await transcript(owner, a.id)
            await transcript(other)
            _, _, other_project = await transcript(owner, b.id)
            _, _, other_session = await transcript(owner, a.id)
            state = await prepare(request, owner, a.id)
            assert "做饭不要放花生" in state["history_context"]
            assert len(state["history"]) == 12 and "经济" in state["history"][-1]["content"]
            assert messages[0].id in [
                UUID(r["message_id"]) for r in state["context_usage"]["references"]
            ]
            allowed = {str(m.id) for m in messages}
            assert all(r["message_id"] in allowed for r in state["context_usage"]["references"])
            for uid, pid in [(other, a.id), (owner, b.id), (owner, None)]:
                with pytest.raises(NotFoundError):
                    await prepare(request, uid, pid)
            with pytest.raises(NotFoundError):
                await prepare(
                    {**request, "user_message_id": other_session["user_message_id"]}, owner, a.id
                )
            with pytest.raises(NotFoundError):
                await prepare({**request, "prompt": "替换请求"}, owner, a.id)
            async with get_worker_db_context() as db:
                assert await db.scalar(select(func.count()).select_from(MemoryItem)) == 0

    asyncio.run(check())


def test_backfill_cursor_source_invalidation_and_rebuild_preserve_raw_messages():
    async def check():
        async with workspace() as (owner, other, kb, foreign, a, b, user, client):
            cid, messages, request = await transcript(owner, a.id)
            before = await prepare(request, owner, a.id)
            await index(cid)
            await index(cid)
            async with get_worker_db_context() as db:
                assert (
                    await db.scalar(
                        select(func.count()).select_from(Block).where(Block.conversation_id == cid)
                    )
                    == 2
                )
                job = await db.get(Job, cid)
                assert job.cursor_id == messages[15].id
            after = await prepare(request, owner, a.id)
            assert after["context_usage"]["summary_blocks"] > 0
            assert "不能" not in after["history_context"]  # The original wording stays exact.
            async with get_worker_db_context() as db:
                await db.execute(
                    update(Message)
                    .where(Message.id == messages[0].id)
                    .values(content="做饭预算五十元，不要花生")
                )
            async with get_worker_db_context() as db:
                assert (await db.get(Message, messages[0].id)).content == "做饭预算五十元，不要花生"
                assert (
                    await db.scalar(
                        select(func.count()).select_from(Block).where(Block.conversation_id == cid)
                    )
                    == 0
                )
                job = await db.get(Job, cid)
                assert job.cursor_id is None and job.revision == 2
            with pytest.raises(BadRequestError):
                await context.revalidate(request, before, owner, a.id)
            await index(cid)
            async with get_worker_db_context() as db:
                assert (
                    await db.scalar(
                        select(func.count()).select_from(Block).where(Block.conversation_id == cid)
                    )
                    == 1
                )
                await db.execute(delete(Message).where(Message.id == messages[0].id))
            async with get_worker_db_context() as db:
                assert (
                    await db.scalar(
                        select(func.count()).select_from(Block).where(Block.conversation_id == cid)
                    )
                    == 0
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(Message)
                        .where(Message.conversation_id == cid)
                    )
                    == len(messages) - 1
                )

    asyncio.run(check())


def test_edit_during_model_call_fences_stale_batch_then_recovers():
    async def check():
        async with workspace() as (owner, other, kb, foreign, a, b, user, client):
            cid, messages, request = await transcript(owner, a.id)
            await prepare(request, owner, a.id)

            async def edit():
                async with get_worker_db_context() as db:
                    await db.execute(
                        update(Message)
                        .where(Message.id == messages[0].id)
                        .values(content="最新做饭限制")
                    )

            await index(cid, edit)
            async with get_worker_db_context() as db:
                assert (
                    await db.scalar(
                        select(func.count()).select_from(Block).where(Block.conversation_id == cid)
                    )
                    == 0
                )
            await index(cid)
            async with get_worker_db_context() as db:
                block = await db.scalar(select(Block).where(Block.conversation_id == cid))
                assert "最新做饭限制" in str(block.notes)

    asyncio.run(check())


def test_original_passage_disclosure_enforces_scope_and_marks_changed_source():
    async def check():
        async with workspace() as (owner, other, kb, foreign, a, b, user, client):
            cid, messages, request = await transcript(owner, a.id)
            prepared = await prepare(request, owner, a.id)
            config = EffectiveAnswerConfig(
                **resolve_generation_config({}).model_dump(), context=prepared["context_usage"]
            )
            async with get_worker_db_context() as db:
                answer = Message(
                    conversation_id=cid,
                    role="assistant",
                    content="不能放花生",
                    effective_config=config.model_dump(mode="json"),
                    created_at=datetime.now(UTC),
                )
                db.add(answer)
                await db.flush()
            url = f"/api/v1/chat/conversations/{cid}/messages/{answer.id}/context"
            response = await client.get(url, headers=header(a))
            assert response.status_code == 200, response.text
            assert "做饭不要放花生" in str(response.json())
            assert (await client.get(url, headers=header(b))).status_code == 404
            async with get_worker_db_context() as db:
                await db.execute(delete(Message).where(Message.id == messages[0].id))
            response = await client.get(url, headers=header(a))
            lost = next(
                i for i in response.json()["items"] if i["message_id"] == str(messages[0].id)
            )
            assert lost["state"] == "changed" and lost["content"] is None

    asyncio.run(check())


def test_strict_knowledge_history_does_not_promote_prior_assistant_answers():
    async def check():
        async with workspace() as (owner, other, kb, foreign, a, b, user, client):
            _, _, request = await transcript(owner, a.id)
            state = await prepare(
                {**request, "knowledge_base_ids": [str(kb.id)], "knowledge_strict": True},
                owner,
                a.id,
            )
            assert all(item["role"] == "user" for item in state["rewrite_history"])
            assert '"role": "assistant"' not in state["history_context"]

    asyncio.run(check())


def test_no_future_or_unfinished_assistant_content_is_loaded():
    async def check():
        async with workspace() as (owner, other, kb, foreign, a, b, user, client):
            cid, messages, request = await transcript(owner, a.id)
            async with get_worker_db_context() as db:
                db.add(
                    Message(
                        conversation_id=cid,
                        role="user",
                        content="做饭未来机密",
                        created_at=datetime.now(UTC) + timedelta(days=1),
                    )
                )
                db.add(
                    AgentRun(
                        user_id=owner,
                        project_id=a.id,
                        conversation_id=cid,
                        user_message_id=messages[0].id,
                        assistant_message_id=messages[1].id,
                        idempotency_key=uuid4(),
                        request_hash="x" * 64,
                        request={},
                        effective_config={},
                        status="running",
                    )
                )
            state = await prepare(request, owner, a.id)
            assert "未来机密" not in str(state) and "建议清蒸鱼" not in state["history_context"]
            await index(cid)
            async with get_worker_db_context() as db:
                assert (
                    await db.scalar(
                        select(func.count()).select_from(Block).where(Block.conversation_id == cid)
                    )
                    == 0
                )

    asyncio.run(check())


def test_empty_attachment_prompt_is_validated_without_requiring_text():
    async def check():
        async with workspace() as (owner, other, kb, foreign, a, b, user, client):
            _, messages, request = await transcript(owner, a.id, count=0)
            async with get_worker_db_context() as db:
                await db.execute(
                    update(Message).where(Message.id == messages[0].id).values(content="")
                )
            request = {**request, "prompt": "", "file_ids": [str(uuid4())]}
            state = await prepare(request, owner, a.id)
            await context.revalidate(request, state, owner, a.id)

    asyncio.run(check())


def test_context_migration_rebuild_preserves_existing_transcript():
    from alembic.config import Config

    from alembic import command

    def migrate(direction, revision):
        # Resolve from the test file in CI, without loading a repository .env.
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / "alembic.ini"))
        config.set_main_option("script_location", str(root / "alembic"))
        getattr(command, direction)(config, revision)

    async def check():
        async with workspace() as (owner, other, kb, foreign, a, b, user, client):
            cid, messages, request = await transcript(owner, a.id)
            await prepare(request, owner, a.id)
            await index(cid)
            try:
                await asyncio.to_thread(migrate, "downgrade", "0045_mem0_memory")
                async with get_worker_db_context() as db:
                    rows = list(
                        await db.scalars(
                            select(Message)
                            .where(Message.conversation_id == cid)
                            .order_by(Message.created_at)
                        )
                    )
                    assert [m.content for m in rows] == [m.content for m in messages]
            finally:
                await asyncio.to_thread(migrate, "upgrade", "head")
            await prepare(request, owner, a.id)
            await index(cid)
            async with get_worker_db_context() as db:
                assert (
                    await db.scalar(
                        select(func.count()).select_from(Block).where(Block.conversation_id == cid)
                    )
                    == 1
                )

    asyncio.run(check())


@pytest.mark.skipif(
    os.getenv("RUN_LOCAL_CONTEXT_EMBED_TESTS") != "1", reason="requires cached local BGE model"
)
def test_real_local_vectors_and_pgvector_recover_topic_after_mixed_discussion():
    async def check():
        async with workspace() as (owner, other, kb, foreign, a, b, user, client):
            cid, messages, request = await transcript(owner, a.id)
            await prepare(request, owner, a.id)
            original = worker.summarize

            async def extract(data, config, allow):
                return await original(data, config, False)

            with patch.object(worker, "summarize", extract):
                await worker.execute(cid, AsyncMock())
            result = await prepare(request, owner, a.id)
            assert result["context_usage"]["retrieval"] == "hybrid"
            assert "不要放花生" in result["history_context"]

    asyncio.run(check())


def test_summary_labels_aid_search_but_only_original_passages_reach_answer_context():
    async def check():
        async with workspace() as (owner, other, kb, foreign, a, b, user, client):
            cid, messages, request = await transcript(owner, a.id)
            await prepare(request, owner, a.id)
            summary = [
                {
                    "source": 0,
                    "topic": "餐食禁忌",
                    "summary": "餐食禁忌涉及过敏原",
                    "quote": "做饭不要放花生",
                    "kind": "constraint",
                }
            ]
            with (
                patch.object(worker, "summarize", AsyncMock(return_value=(summary, "summary", {}))),
                patch.object(worker, "encode_note", side_effect=RuntimeError("offline")),
            ):
                await worker.execute(cid, AsyncMock())
            async with get_worker_db_context() as db:
                await db.execute(
                    update(Message).where(Message.id == messages[-1].id).values(content="餐食禁忌")
                )
            state = await prepare({**request, "prompt": "餐食禁忌"}, owner, a.id)
            assert "做饭不要放花生" in state["history_context"]
            assert "餐食禁忌涉及过敏原" not in state["history_context"]

    asyncio.run(check())
