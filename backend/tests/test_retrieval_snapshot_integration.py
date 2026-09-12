"""Submission/execution stability against a disposable database."""

import asyncio
import os
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.core.exceptions import BadRequestError, NotFoundError
from app.db.session import get_worker_db_context
from app.schemas.knowledge import RetrievalConfig
from app.services.knowledge import KnowledgeService
from app.worker.agent_runs import try_run
from tests.test_agent_runs_integration import create, get, users
from tests.test_knowledge_collaboration import fixture, record_search, roles

pytestmark = pytest.mark.skipif(os.getenv("RUN_TASK_DB_TESTS") != "1", reason="isolated DB only")


async def set_config(uid, config):
    async with get_worker_db_context() as db:
        await KnowledgeService(db, uid).update_retrieval_config(config)


@pytest.mark.parametrize("mode", ["standard", "knowledge_collaboration"])
def test_fixed_parameters_survive_default_changes_and_worker_persistence(mode):
    async def check():
        async with fixture() as (uid, other, bid, source):
            original = RetrievalConfig(mode="keyword", result_limit=9)
            await set_config(uid, original)
            key = uuid4()
            run = await create(uid, idempotency_key=key, mode=mode, knowledge_base_ids=[bid])
            snapshot = run.request["retrieval_snapshot"]
            await set_config(uid, RetrievalConfig(mode="semantic", result_limit=2))
            same = await create(uid, idempotency_key=key, mode=mode, knowledge_base_ids=[bid])
            assert same.id == run.id and same.request["retrieval_snapshot"] == snapshot
            used = []

            async def search(self, ids, query, **kwargs):
                config = kwargs["config"]
                used.append(config.model_dump())
                await set_config(uid, RetrievalConfig(result_limit=1))
                return record_search(kwargs, [source])

            with (
                patch("app.services.knowledge.KnowledgeService.search", search),
                patch("app.services.knowledge_collaboration.run_role", side_effect=roles([])),
                patch(
                    "app.services.agent_run_graph.grounded_answer", return_value=("answer", [], {})
                ),
            ):
                await try_run(run.id)
            saved = await get(uid, run.id)
            assert saved.status == "completed", saved.error
            assert used and all(c == snapshot["config"] for c in used)
            assert len(used) == (3 if mode == "knowledge_collaboration" else 1)
            assert snapshot["config"]["result_limit"] == (
                5 if mode == "knowledge_collaboration" else 9
            )
            records = saved.result["retrieval_runs"]
            assert len(records) == len(used)
            assert all(r["configuration_id"] == snapshot["configuration_id"] for r in records)
            with pytest.raises(NotFoundError):
                await get(other, run.id)
            newer = await create(uid, mode=mode, knowledge_base_ids=[bid])
            assert newer.request["retrieval_snapshot"]["config"]["result_limit"] == 1

    asyncio.run(check())


def test_override_does_not_write_account_preferences():
    async def check():
        async with fixture() as (uid, _, bid, _):
            defaults = RetrievalConfig()
            await set_config(uid, defaults)
            run = await create(
                uid,
                knowledge_base_ids=[bid],
                retrieval_config=RetrievalConfig(mode="keyword", result_limit=3),
            )
            assert run.request["retrieval_snapshot"]["origin"] == "task_override"
            assert run.request["retrieval_snapshot"]["config"]["result_limit"] == 3
            async with get_worker_db_context() as db:
                assert await KnowledgeService(db, uid).get_retrieval_config() == defaults
        async with users() as (uid, _):
            with pytest.raises(BadRequestError):
                await create(uid, retrieval_config=RetrievalConfig())

    asyncio.run(check())
