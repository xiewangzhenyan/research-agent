# ruff: noqa: SIM117 - Chinese fixtures; explicit assertion scope
"""Collaboration boundaries, revision budget and recovery; isolated DB only."""

import asyncio
import os
from collections import Counter
from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.core.exceptions import BadRequestError, NotFoundError
from app.db.models.knowledge import KnowledgeBase, KnowledgeDocument
from app.db.session import get_worker_db_context
from app.schemas.knowledge import RetrievalConfig
from app.services.knowledge_answer import ABSTENTION
from app.services.knowledge_collaboration import (
    build_collaboration_graph,
    merge_sources,
    run_role,
)
from app.services.knowledge_index import MODEL
from app.services.model_config import resolve_generation_config
from app.worker.agent_runs import try_run
from tests.test_agent_runs_integration import create, get, users

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_TASK_DB_TESTS") != "1", reason="requires disposable database"
)


@asynccontextmanager
async def fixture():
    async with users() as (uid, other):
        bid, did = uuid4(), uuid4()
        async with get_worker_db_context() as db:
            db.add(KnowledgeBase(id=bid, user_id=uid, name="Collaboration fixture"))
            await db.flush()
            db.add(
                KnowledgeDocument(
                    id=did,
                    knowledge_base_id=bid,
                    filename="policy.txt",
                    storage_path="",
                    size=10,
                    sha256=str(uuid4()),
                    status="ready",
                    embedding_model=MODEL,
                )
            )
        source = {
            "id": str(uuid4()),
            "document_id": str(did),
            "index": 1,
            "content": "服务期限为30天，不支持自动续期。",
            "revision": 1,
        }
        yield uid, other, bid, source


def record_search(kwargs, sources):
    config = kwargs.get("config") or RetrievalConfig()
    config = config.model_copy(update={"result_limit": kwargs.get("top_k") or config.result_limit})
    kwargs["diagnostics"].update(config=config.model_dump(), engine="legacy", returned=len(sources))
    return sources


def search_result(sources):
    async def call(*args, **kwargs):
        return record_search(kwargs, sources)

    return call


def answer(quote="服务期限为30天，不支持自动续期。"):
    return {
        "sufficient": True,
        "claims": [
            {"text": "服务期限为30天，不支持自动续期。", "evidence": [{"index": 1, "quote": quote}]}
        ],
    }


def roles(calls, reject=False, invalid=False):
    async def invoke(role, payload, config, usage, *, validate=None, request_limit=12):
        if validate:
            await validate()
        calls.append(role)
        if role == "planner":
            result = {"objective": "核对条款", "queries": ["服务期限", "自动续期"]}
        elif role == "critic":
            result = {"approved": not reject, "issues": ["请核对续期条件"] if reject else []}
        else:
            result = answer(
                "不存在的引文"
                if invalid and role == "writer"
                else "服务期限为30天，不支持自动续期。"
            )
        return result, {"requests": usage.get("requests", 0) + 1}

    return invoke


@pytest.mark.parametrize("reject,invalid", [(False, False), (True, False), (False, True)])
def test_full_worker_collaboration_and_bounded_revision(reject, invalid):
    async def check():
        async with fixture() as (uid, other, bid, source):
            run = await create(uid, mode="knowledge_collaboration", knowledge_base_ids=[bid])
            calls, queries = [], []

            async def search(self, ids, query, **kwargs):
                assert self.user_id == uid and ids == [bid]
                queries.append(query)
                return record_search(kwargs, [source])

            with (
                patch(
                    "app.services.knowledge_collaboration.run_role",
                    side_effect=roles(calls, reject, invalid),
                ),
                patch("app.services.knowledge.KnowledgeService.search", search),
            ):
                await try_run(run.id)
            saved = await get(uid, run.id)
            assert saved.status == "completed", saved.error
            assert saved.request["tools"] == []
            assert queries[0] == run.request["prompt"]
            assert Counter(calls)["writer"] == (2 if reject or invalid else 1)
            assert saved.result["collaboration"]["revisions"] == (1 if reject or invalid else 0)
            if reject or invalid:
                assert saved.result["content"] == ABSTENTION
                assert saved.result["citations"] == []
            else:
                assert saved.result["citations"][0]["quotes"] == [source["content"]]
                assert calls == ["planner", "researcher", "writer", "critic"]
            with pytest.raises(NotFoundError):
                await get(other, run.id)

    asyncio.run(check())


def test_submission_requires_owned_knowledge_and_no_extra_tools():
    async def check():
        async with fixture() as (uid, other, bid, _):
            with pytest.raises(BadRequestError):
                await create(uid, mode="knowledge_collaboration")
            with pytest.raises(BadRequestError):
                await create(
                    uid,
                    mode="knowledge_collaboration",
                    knowledge_base_ids=[bid],
                    tools=["current_datetime"],
                )
            with pytest.raises(NotFoundError):
                await create(other, mode="knowledge_collaboration", knowledge_base_ids=[bid])
            key = uuid4()
            first = await create(uid, idempotency_key=key)
            same = await create(uid, idempotency_key=key, mode="standard")
            assert same.id == first.id

    asyncio.run(check())


def test_checkpoint_resumes_failed_role_without_repeating_completed_roles():
    async def check():
        async with fixture() as (uid, _, bid, source):
            saver, calls = InMemorySaver(), []
            fail = True
            normal = roles(calls)

            async def invoke(role, *args):
                nonlocal fail
                if role == "writer" and fail:
                    fail = False
                    raise RuntimeError("interrupted generation")
                return await normal(role, *args)

            async def emit(*args):
                pass

            graph = build_collaboration_graph(
                saver,
                user_id=uid,
                configuration=resolve_generation_config({}).model_dump(),
                emit=emit,
            )
            cfg = {"configurable": {"thread_id": str(uuid4())}}
            with (
                patch("app.services.knowledge_collaboration.run_role", side_effect=invoke),
                patch(
                    "app.services.knowledge.KnowledgeService.search",
                    side_effect=search_result([source]),
                ),
            ):
                with pytest.raises(RuntimeError):
                    await graph.ainvoke({"prompt": "条款？", "base_ids": [str(bid)]}, cfg)
                result = await graph.ainvoke(None, cfg)
            assert calls == ["planner", "researcher", "writer", "critic"]
            assert result["citations"]

    asyncio.run(check())


def test_deleted_source_revokes_next_role_access():
    async def check():
        async with fixture() as (uid, _, bid, source):
            calls = []
            normal = roles(calls)

            async def invoke(role, *args):
                result = await normal(role, *args)
                if role == "researcher":
                    async with get_worker_db_context() as db:
                        doc = await db.get(KnowledgeDocument, source["document_id"])
                        await db.delete(doc)
                return result

            async def emit(*args):
                pass

            graph = build_collaboration_graph(
                InMemorySaver(),
                user_id=uid,
                configuration=resolve_generation_config({}).model_dump(),
                emit=emit,
            )
            with (
                patch("app.services.knowledge_collaboration.run_role", side_effect=invoke),
                patch(
                    "app.services.knowledge.KnowledgeService.search",
                    side_effect=search_result([source]),
                ),
            ):
                with pytest.raises(NotFoundError):
                    await graph.ainvoke(
                        {"prompt": "条款？", "base_ids": [str(bid)]},
                        {"configurable": {"thread_id": str(uuid4())}},
                    )
            assert "writer" not in calls

    asyncio.run(check())


def test_empty_search_skips_unnecessary_model_calls():
    async def check():
        async with fixture() as (uid, _, bid, _):
            calls = []
            run = await create(uid, mode="knowledge_collaboration", knowledge_base_ids=[bid])
            with (
                patch("app.services.knowledge_collaboration.run_role", side_effect=roles(calls)),
                patch(
                    "app.services.knowledge.KnowledgeService.search", side_effect=search_result([])
                ),
            ):
                await try_run(run.id)
            saved = await get(uid, run.id)
            assert saved.status == "completed", saved.error
            assert saved.result["content"] == ABSTENTION
            assert calls == ["planner"]

    asyncio.run(check())


def test_role_adapter_uses_structured_output_without_general_tools():
    def model(messages, info):
        assert not info.function_tools
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name, {"objective": "核对条款", "queries": ["服务期限"]}
                )
            ]
        )

    async def check():
        with patch(
            "app.services.knowledge_collaboration._build_model", return_value=FunctionModel(model)
        ):
            result, usage = await run_role(
                "planner", {"question": "条款"}, resolve_generation_config({}), {}
            )
        assert result["queries"] == ["服务期限"]
        assert usage["requests"] == 1

    asyncio.run(check())


def test_source_merge_retains_multiple_queries_and_unique_indices():
    a = [{"id": str(i), "content": "A", "index": i} for i in range(10)]
    b = [{"id": "second", "content": "B", "index": 1}, a[0]]
    result = merge_sources([a, b])
    assert len(result) == 10
    assert result[1]["id"] == "second"
    assert [s["index"] for s in result] == list(range(1, 11))
    assert len({s["id"] for s in result}) == 10


def test_cancel_collaboration_prevents_review_and_result():
    from app.services.agent_run import AgentRunService

    async def check():
        async with fixture() as (uid, _, bid, source):
            calls, entered, stopped = [], asyncio.Event(), asyncio.Event()
            normal = roles(calls)

            async def invoke(role, *args):
                if role == "writer":
                    entered.set()
                    try:
                        await asyncio.sleep(30)
                    finally:
                        stopped.set()
                return await normal(role, *args)

            run = await create(uid, mode="knowledge_collaboration", knowledge_base_ids=[bid])
            with (
                patch("app.services.knowledge_collaboration.run_role", side_effect=invoke),
                patch(
                    "app.services.knowledge.KnowledgeService.search",
                    side_effect=search_result([source]),
                ),
            ):
                work = asyncio.create_task(try_run(run.id))
                await asyncio.wait_for(entered.wait(), 10)
                async with get_worker_db_context() as db:
                    await AgentRunService(db, uid).cancel(run.id)
                await asyncio.wait_for(work, 10)
            saved = await get(uid, run.id)
            assert stopped.is_set()
            assert saved.status == "cancelled"
            assert saved.result is None
            assert "critic" not in calls

    asyncio.run(check())
