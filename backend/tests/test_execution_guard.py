"""Observe native tool cycles, changed results and persisted-message recovery."""

import json

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from app.agents.runtime import ToolRegistry, run_tools
from app.services.execution_guard import ExecutionStalledError, RepeatedToolResultGuard
from app.services.model_config import resolve_generation_config
from tests.model_fixtures import ScriptedModel, model_response, text_part, tool_call


def history(results):
    messages = [HumanMessage(content="research")]
    for i, result in enumerate(results):
        messages.extend(
            [
                model_response(parts=[tool_call("lookup", {"query": "same"}, str(i))]),
                ToolMessage(content=json.dumps(result), name="lookup", tool_call_id=str(i)),
            ]
        )
    return messages


@pytest.mark.anyio
async def test_real_agent_stops_before_fourth_identical_tool_execution():
    calls = []
    agent = ToolRegistry(
        ScriptedModel(lambda m, i: model_response(parts=[tool_call("lookup", {"query": "same"})])),
        resolve_generation_config({}),
    )

    @agent.register_plain
    def lookup(query: str) -> str:
        calls.append(query)
        return "no new evidence"

    with pytest.raises(ExecutionStalledError):
        await run_tools(agent, "research", request_limit=10)
    assert calls == ["same"] * 3


@pytest.mark.anyio
async def test_changed_results_are_progress_and_can_complete():
    calls = []

    def model(messages, info):
        return (
            model_response(parts=[text_part("finished")])
            if len(calls) >= 5
            else model_response(parts=[tool_call("lookup", {})])
        )

    agent = ToolRegistry(ScriptedModel(model), resolve_generation_config({}))

    @agent.register_plain
    def lookup() -> str:
        calls.append(len(calls))
        return f"new evidence {len(calls)}"

    assert (await run_tools(agent, "research"))["output"] == "finished"
    assert len(calls) == 5


def test_reconstructed_history_detects_repeated_cycle_after_restart():
    with pytest.raises(ExecutionStalledError):
        RepeatedToolResultGuard().check(history(["a", "b", "a", "b", "a"]))


@pytest.mark.parametrize("barrier", ["message", "clarification"])
def test_new_user_input_resets_observations(barrier):
    messages = history(["a"] * 3)
    messages.append(
        HumanMessage(content="try again")
        if barrier == "message"
        else ToolMessage(content="new constraints", name="ask_user", tool_call_id="answer")
    )
    RepeatedToolResultGuard().check(messages)


def test_observations_are_bounded_and_state_is_per_run():
    guard = RepeatedToolResultGuard()
    guard.check(history(["old"] * 3 + list(range(12))))
    guard.check(history(["a", "a"]))
