"""Regression coverage for authorized models and parameters across answer paths."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from pydantic_ai.models.test import TestModel

from app.agents.assistant import get_agent
from app.agents.tool_catalog import CHAT_TOOL_NAMES
from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.services import agent_capabilities, agent_session, knowledge_answer
from app.services.model_config import resolve_generation_config


@pytest.fixture(autouse=True)
def model_policy(monkeypatch):
    monkeypatch.setattr(settings, "AI_MODEL", "reasoning")
    monkeypatch.setattr(settings, "AI_AVAILABLE_MODELS", ["reasoning", "standard", "unknown-alias"])
    monkeypatch.setattr(
        settings,
        "AI_MODEL_CONTROLS",
        {"reasoning": ["thinking_effort"], "standard": ["temperature"]},
    )
    monkeypatch.setattr(settings, "AI_THINKING_ENABLED", True)
    monkeypatch.setattr(settings, "AI_THINKING_EFFORT", "medium")
    monkeypatch.setattr(settings, "AI_TEMPERATURE", 0.7)


@pytest.mark.parametrize(
    "data",
    [
        {"model": "not-authorized"},
        {"model": 123},
        {"model": ""},
        {"temperature": True},
        {"temperature": "0.2"},
        {"temperature": float("nan")},
        {"temperature": float("inf")},
        {"temperature": -0.1},
        {"temperature": 2.1},
        {"model": "reasoning", "temperature": 0.2},
        {"model": "standard", "thinking_effort": "high"},
        {"thinking_effort": "invalid"},
        {"thinking_effort": True},
    ],
)
def test_rejects_invalid_or_unapproved_controls(data):
    with pytest.raises(BadRequestError):
        resolve_generation_config(data)


def test_model_specific_defaults_and_explicit_off():
    assert resolve_generation_config({}).provider_settings()["openai_reasoning_effort"] == "medium"
    assert resolve_generation_config({"thinking_effort": "off"}).provider_settings() == {}
    assert resolve_generation_config({"model": "standard"}).provider_settings() == {
        "temperature": 0.7
    }
    assert resolve_generation_config({"model": "standard", "temperature": 0}).temperature == 0
    assert resolve_generation_config({"model": "unknown-alias"}).provider_settings() == {}


def test_policy_snapshot_changes_when_defaults_change(monkeypatch):
    before = resolve_generation_config({}).policy_version
    monkeypatch.setattr(settings, "AI_THINKING_EFFORT", "high")
    assert resolve_generation_config({}).policy_version != before


def test_registered_tools_and_prompt_match_real_runtime():
    with patch("app.agents.assistant._build_model", return_value=TestModel()):
        assistant = get_agent()
        assert set(assistant.agent._function_toolset.tools) == set(CHAT_TOOL_NAMES)
        assert "You have a `run_python`" not in assistant.system_prompt
        assert "You can render charts" not in assistant.system_prompt
        assert assistant.agent.model_settings == assistant.configuration.provider_settings()


@pytest.mark.anyio
@pytest.mark.parametrize("data", [{"model": "foreign"}, {"temperature": 0.2}])
async def test_session_rejects_before_database_retrieval_or_model_call(data):
    session = agent_session.AgentSession(AsyncMock(), SimpleNamespace(id=uuid4(), full_name="Test"))
    with patch.object(agent_session, "get_db_context") as database:
        with pytest.raises(BadRequestError):
            await session.process_message({"message": "test", **data})
        database.assert_not_called()


@pytest.mark.anyio
async def test_grounded_and_rewrite_receive_same_provider_settings():
    config = resolve_generation_config({"model": "standard", "temperature": 0.15})
    agent = MagicMock()
    agent.run = AsyncMock(
        return_value=SimpleNamespace(output=knowledge_answer.GroundedAnswer(sufficient=False))
    )
    with (
        patch.object(knowledge_answer, "Agent", return_value=agent) as factory,
        patch.object(knowledge_answer, "_build_model"),
    ):
        await knowledge_answer.grounded_answer(
            "q", [{"index": 1, "content": "data"}], "standard", configuration=config
        )
        assert factory.call_args.kwargs["model_settings"] == {"temperature": 0.15}
        agent.run.return_value = SimpleNamespace(
            output=knowledge_answer.RewrittenQuery(query="follow up")
        )
        await knowledge_answer.rewrite_query(
            "q", [{"role": "user", "content": "history"}], "standard", configuration=config
        )
        assert factory.call_args.kwargs["model_settings"] == {"temperature": 0.15}


@pytest.mark.anyio
@pytest.mark.parametrize("strict", [False, True])
async def test_session_forwards_and_persists_effective_configuration(strict):
    user = SimpleNamespace(id=uuid4(), full_name="Test")
    session = agent_session.AgentSession(AsyncMock(), user)
    db = AsyncMock()

    @asynccontextmanager
    async def database():
        yield db

    service = AsyncMock()
    knowledge = AsyncMock()
    knowledge.search.return_value = []
    runtime = MagicMock()
    runtime.model_name = "standard"

    @asynccontextmanager
    async def iteration(*args, **kwargs):
        yield SimpleNamespace(result=SimpleNamespace(output="answer"))

    runtime.agent.iter = iteration
    session._stream_agent_run = AsyncMock()
    session._build_multimodal_input = AsyncMock(return_value="question")
    with (
        patch.object(agent_session, "get_db_context", database),
        patch.object(agent_session, "get_conversation_service", return_value=service),
        patch.object(agent_session, "KnowledgeService", return_value=knowledge),
        patch.object(
            agent_session, "persist_user_turn", AsyncMock(return_value=(str(uuid4()), False, None))
        ),
        patch.object(
            agent_session, "persist_assistant_turn", AsyncMock(return_value="saved")
        ) as persist,
        patch(
            "app.services.memory.MemoryService.recall",
            AsyncMock(
                return_value={
                    "status": "strict_knowledge" if strict else "disabled",
                    "items": [],
                    "omitted": 0,
                    "estimated_tokens": 0,
                }
            ),
        ),
        patch.object(agent_session, "get_agent", return_value=runtime) as factory,
        patch.object(agent_session, "send_event", AsyncMock()) as events,
        patch.object(
            knowledge_answer, "rewrite_query", AsyncMock(return_value=("question", "original"))
        ),
        patch.object(
            knowledge_answer, "grounded_answer", AsyncMock(return_value=("answer", [], {}))
        ) as grounded,
    ):
        await session.process_message(
            {
                "message": "question",
                "model": "standard",
                "temperature": 0.25,
                "knowledge_base_ids": [str(uuid4())] if strict else [],
                "knowledge_strict": strict,
            }
        )
        config = factory.call_args.kwargs["configuration"]
        assert config.temperature == 0.25
        if strict:
            assert grounded.call_args.kwargs["configuration"] == config
        assert {
            k: v for k, v in persist.call_args.kwargs["effective_config"].items() if k != "memory"
        } == config.model_dump()
        assert persist.call_args.kwargs["effective_config"]["memory"]["status"] == (
            "strict_knowledge" if strict else "disabled"
        )
        assert any(call.args[1] == "effective_config" for call in events.call_args_list)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload,status",
    [
        (
            {
                "status": "healthy",
                "model": agent_capabilities.RERANK_MODEL,
                "revision": agent_capabilities.RERANK_REVISION,
            },
            "healthy",
        ),
        ({"status": "healthy", "model": "wrong", "revision": "wrong"}, "version_mismatch"),
        ({"status": "failed", "detail": "secret internal address"}, "unavailable"),
    ],
)
async def test_discovery_redacts_and_checks_reranker_version(payload, status, monkeypatch):
    monkeypatch.setattr(agent_capabilities, "_health_cache", None)
    client = AsyncMock()
    client.get.return_value = httpx.Response(
        200, json=payload, request=httpx.Request("GET", "http://test/health")
    )
    with patch.object(agent_capabilities.httpx, "AsyncClient") as factory:
        factory.return_value.__aenter__.return_value = client
        info = await agent_capabilities.get_capabilities()
        again = await agent_capabilities.get_capabilities()
    assert info.rerank.status == status and again.rerank == info.rerank
    assert info.embedding.status == "not_checked"
    client.get.assert_awaited_once()
    serialized = info.model_dump_json()
    assert "secret internal address" not in serialized
    assert "http://" not in serialized and "api_key" not in serialized
    assert not next(c for c in info.capabilities if c.id == "run_python").available


@pytest.mark.anyio
async def test_discovery_requires_login(client):
    response = await client.get("/api/v1/agent/capabilities")
    assert response.status_code == 401
