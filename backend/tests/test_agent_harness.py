"""Shared role construction, lifecycle ordering and isolated child handoffs."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from app.agents.factory import AgentDefinition, create_agent
from app.agents.policy import ExecutionLimits, ExecutionPolicy, ToolRetry
from app.agents.runtime import run_tools
from app.core.exceptions import AuthorizationError, RateLimitError
from app.services.agent_handoff import evidence_handoff, review_handoff
from app.services.knowledge_collaboration import role_payload, run_role
from app.services.model_config import resolve_generation_config
from tests.model_fixtures import ScriptedModel, model_response, tool_call


class Result(BaseModel):
    value: str


@pytest.mark.anyio
async def test_factory_uses_same_transport_and_restricts_schema_roles():
    seen = []

    def model(messages, info):
        seen.append((messages, info))
        return model_response([tool_call("Result", {"value": "done"})])

    configuration = resolve_generation_config({})
    definition = AgentDefinition(
        "researcher",
        "source-only",
        Result,
        limits=ExecutionLimits(requests=2, timeout=5),
        output_tokens=600,
    )
    agent = create_agent(definition, configuration, model=ScriptedModel(model))
    with pytest.raises(ValueError, match="executable tools"):
        agent.registry()
    result = await agent.structured("question", request_limit=99)
    assert result.output.value == "done"
    assert seen[0][0][0].content == "source-only"
    assert seen[0][1].model_settings["max_tokens"] == 600
    with pytest.raises(RateLimitError):
        await agent.structured("question", usage={"requests": 2}, request_limit=99)
    assert len(seen) == 1


@pytest.mark.anyio
async def test_graph_role_cannot_expand_its_definition_budget():
    calls = []

    def model(messages, info):
        return model_response([tool_call("lookup", {})])

    agent = create_agent(
        AgentDefinition("assistant", "assist", limits=ExecutionLimits(requests=1)),
        resolve_generation_config({}),
        model=ScriptedModel(model),
    )
    registry = agent.registry()

    @registry.register_plain
    async def lookup() -> str:
        calls.append(True)
        return "result"

    with pytest.raises(RateLimitError):
        await run_tools(registry, "research", request_limit=99)
    assert calls == [True]


@pytest.mark.anyio
async def test_policy_revalidates_scope_before_model_budget_or_tool_work():
    validate = AsyncMock(side_effect=AuthorizationError(message="revoked"))
    policy = ExecutionPolicy(resolve_generation_config({}), validate=validate)
    with pytest.raises(AuthorizationError):
        await policy.before_model([], [], {"requests": 100})
    with pytest.raises(AuthorizationError):
        await policy.before_tool({"name": "unknown"}, {"tool_calls": 100}, {})
    assert validate.await_count == 2


def test_policy_never_converts_authorization_or_service_failure_to_retry():
    assert ExecutionPolicy.tool_error(ToolRetry("fix input")) == "fix input"
    for exc in (AuthorizationError(), RuntimeError("service failed")):
        with pytest.raises(type(exc)):
            ExecutionPolicy.tool_error(exc)


@pytest.mark.anyio
async def test_role_prompt_drops_parent_history_credentials_and_internal_source_fields():
    def model(messages, info):
        payload = json.loads(messages[-1].content)
        assert set(payload) == {"question", "sources"}
        assert payload["sources"] == [
            {"id": "source", "index": 1, "content": "public", "title": "Policy"}
        ]
        assert not info.function_tools
        return model_response([tool_call(info.output_tools[0].name, {"sufficient": False})])

    with patch(
        "app.services.knowledge_collaboration._build_model", return_value=ScriptedModel(model)
    ):
        result, usage = await run_role(
            "researcher",
            {
                "question": "q",
                "history": ["private history"],
                "api_key": "private-key",
                "sources": [
                    {
                        "id": "source",
                        "index": 1,
                        "content": "public",
                        "embedding": [1, 2],
                        "title": "Policy",
                        "storage_path": "/private/file",
                    }
                ],
            },
            resolve_generation_config({}),
            {},
        )
    assert result["sufficient"] is False and usage["requests"] == 1


def test_handoff_rejects_invented_quote_and_keeps_immutable_evidence_identity():
    sources = [
        {
            "id": "source",
            "document_id": "doc",
            "index": 1,
            "revision": 7,
            "file_version": "sha256-value",
            "content": "Service lasts 30 days.",
        }
    ]
    findings = {
        "sufficient": True,
        "claims": [
            {
                "text": "Service lasts 30 days.",
                "evidence": [{"index": 1, "quote": "Service lasts 30 days."}],
            }
        ],
    }
    checked = evidence_handoff("researcher", findings, sources)
    assert checked.validation == "source_quotes_checked"
    assert checked.evidence[0].file_version == "sha256-value" and checked.evidence[0].revision == 7
    assert checked.artifact_ids == []
    findings["claims"][0]["evidence"][0]["quote"] = "Invented source"
    rejected = evidence_handoff("researcher", findings, sources)
    assert rejected.validation == "no_support" and rejected.evidence == []
    assert "Service lasts 30 days" not in rejected.summary


def test_writer_receives_checked_handoff_instead_of_duplicate_free_text_brief():
    handoff = review_handoff({"approved": False, "issues": ["Check condition"]}).model_dump()
    payload = role_payload(
        "writer",
        {
            "question": "q",
            "brief": "raw history",
            "research_handoff": handoff,
            "history": "private",
        },
    )
    assert payload == {"question": "q", "research_handoff": handoff}
    assert handoff["validation"] == "review_rejected"


def test_clarification_policy_removes_mixed_side_effects():
    response = model_response([tool_call("write", {}), tool_call("ask_user", {"questions": []})])
    filtered = ExecutionPolicy(None).after_model(response, {})
    assert [call["name"] for call in filtered.tool_calls] == ["ask_user"]
    assert filtered.content == []


@pytest.mark.parametrize("limits", [{"requests": 0}, {"tools": -1}, {"timeout": 0}])
def test_invalid_execution_limits_fail_before_execution(limits):
    with pytest.raises(ValueError):
        ExecutionLimits(**limits)


def test_work_context_ignores_progress_changes_but_rejects_requirements_or_artifact_changes():
    from app.services.work_task import context_matches, requirements_context

    payload = {
        "version": "work-context-v1",
        "task_id": "task",
        "revision": 2,
        "status": "active",
        "current_message_id": "now",
        "previous_results": [],
        "requirements": [{"version": 1, "message_id": "goal", "requirement": "budget 73"}],
        "progress": [{"status": "running"}],
        "artifacts": [{"id": "file"}],
    }
    old = "data\n" + json.dumps(payload)
    changed = {**payload, "progress": [{"status": "cancelled"}]}
    assert context_matches(old, "data\n" + json.dumps(changed))
    assert not context_matches(old, "data\n" + json.dumps({**payload, "artifacts": []}))
    assert not context_matches(old, "data\n" + json.dumps({**payload, "requirements": []}))
    isolated = requirements_context(old)
    assert "budget 73" in isolated and "progress" not in isolated and "artifacts" not in isolated
    legacy = {key: payload[key] for key in ("task_id", "revision", "previous_results")}
    legacy["requirements"] = [{"version": 1, "requirement": "budget 73"}]
    assert context_matches("legacy\n" + json.dumps(legacy), old)
    assert not context_matches("invalid", old)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure", [AuthorizationError("revoked"), RuntimeError("storage offline")]
)
async def test_capability_runtime_propagates_permission_and_service_failures(failure):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from uuid import uuid4

    from app.services.capability_runtime import install

    aid = str(uuid4())
    asset = SimpleNamespace(kind="skill", description="summary", name="skill")
    service = SimpleNamespace(
        version=AsyncMock(return_value=SimpleNamespace(manifest={"description": "summary"})),
        read_file=AsyncMock(side_effect=failure),
    )

    @asynccontextmanager
    async def db():
        yield None

    calls = []

    def model(messages, info):
        calls.append(True)
        return model_response([tool_call("read_skill_file", {"skill_id": aid})])

    registry = create_agent(
        AgentDefinition("assistant", "assist"),
        resolve_generation_config({}),
        model=ScriptedModel(model),
    ).registry()
    with (
        patch("app.services.capability_runtime.get_worker_db_context", db),
        patch("app.services.capability_runtime.checked", AsyncMock(return_value=(service, asset))),
    ):
        await install(
            registry,
            [{"id": aid, "kind": "skill", "version": 1}],
            user_id=uuid4(),
            project_id=None,
            run_id=uuid4(),
            decisions={},
            emit=AsyncMock(),
        )
        with pytest.raises(type(failure)):
            await run_tools(registry, "read skill")
    assert calls == [True]
