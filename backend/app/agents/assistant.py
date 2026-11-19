"""Assistant configuration and tool registration; LangGraph owns all execution."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.agents.factory import AgentDefinition, create_agent
from app.agents.messages import history_messages
from app.agents.model import build_model as _build_model
from app.agents.policy import ExecutionLimits
from app.agents.prompts import DEFAULT_SYSTEM_PROMPT
from app.agents.runtime import run_tools
from app.agents.tool_catalog import ASK_USER_TOOL, DATETIME_TOOL
from app.agents.tools.ask_user_tool import MAX_QUESTIONS, QuestionItem, format_answers
from app.agents.utils import get_current_datetime
from app.services.model_config import resolve_generation_config

AskUserCallback = Callable[[list[dict[str, Any]]], Awaitable[list[dict[str, Any]]]]


@dataclass
class Deps:
    """Dependencies passed to registered tools via ToolContext."""

    user_id: str | None = None
    user_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    allowed_tools: tuple[str, ...] = (DATETIME_TOOL, ASK_USER_TOOL)
    authorize_tool: Callable[[str], Awaitable[None]] | None = None
    ask_user: AskUserCallback | None = None


class AssistantAgent:
    def __init__(
        self,
        model_name=None,
        temperature=None,
        system_prompt=None,
        thinking_effort=None,
        configuration=None,
        limits=None,
    ):
        self.configuration = configuration or resolve_generation_config(
            {"model": model_name, "temperature": temperature, "thinking_effort": thinking_effort}
        )
        self.model_name = self.configuration.model
        self.temperature = self.configuration.temperature
        self.thinking_effort = self.configuration.thinking_effort
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._agent = None
        self.limits = limits or ExecutionLimits()

    @property
    def agent(self):
        if self._agent is None:
            self._agent = self.registry(Deps())
        return self._agent

    def registry(self, deps):
        registry = create_agent(
            AgentDefinition(name="assistant", system_prompt=self.system_prompt, limits=self.limits),
            self.configuration,
            model=_build_model(self.model_name),
        ).registry(deps)

        async def authorize(name):
            if name not in deps.allowed_tools:
                raise ValueError("Tool not permitted for this task")
            if deps.authorize_tool:
                await deps.authorize_tool(name)

        if DATETIME_TOOL in deps.allowed_tools:

            @registry.register_plain(name=DATETIME_TOOL)
            async def current_datetime() -> dict[str, str]:
                """Get the current date and time."""
                await authorize(DATETIME_TOOL)
                return get_current_datetime()

        if ASK_USER_TOOL in deps.allowed_tools:

            @registry.register_plain(name=ASK_USER_TOOL)
            async def ask_user(questions: list[QuestionItem]) -> str:
                """Ask the user one or more questions and wait for their answers.

                Mark missing_input/ambiguity/conflict for necessary questions; these cannot be skipped.
                Prefer stating reasonable defaults for minor preferences instead of asking.
                Use this when a decision or missing detail would materially change what
                you do next and you cannot reasonably assume it. You may pass several
                questions at once. Prefer answering directly when the request is clear.

                Args:
                    questions: Question text, optional suggested options and allow_custom.

                Returns:
                    A Q/A transcript, with skipped questions marked.
                """
                await authorize(ASK_USER_TOOL)
                if deps.ask_user is None:
                    return "User interaction is unavailable; state a reasonable assumption."
                if not questions:
                    return "No questions were provided."
                payload = [q.model_dump() for q in questions[:MAX_QUESTIONS]]
                return format_answers(payload, await deps.ask_user(payload))

        return registry

    async def execute(self, user_input, *, deps=None, history=None, on_event=None):
        return await run_tools(
            self.registry(deps or Deps()), user_input, history=history or [], on_event=on_event
        )

    async def run(self, user_input, history=None, deps=None):
        active = deps or Deps()
        result = await self.execute(user_input, deps=active, history=history_messages(history))
        return result["output"], result["messages"], active


def get_agent(
    model_name=None, thinking_effort=None, temperature=None, configuration=None, limits=None
):
    return AssistantAgent(
        model_name=model_name,
        thinking_effort=thinking_effort,
        temperature=temperature,
        configuration=configuration,
        limits=limits,
    )


async def run_agent(user_input, history, deps=None):
    return await get_agent().run(user_input, history, deps)
