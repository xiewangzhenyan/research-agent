"""Shared, ordered lifecycle checks; LangGraph remains the execution owner."""

from dataclasses import dataclass

from pydantic import ValidationError

from app.core.exceptions import BadRequestError


class ToolRetry(ValueError):
    """Recoverable tool input error. Authorization/service errors must propagate."""


@dataclass(frozen=True)
class ExecutionLimits:
    requests: int = 12
    tokens: int = 60000
    tools: int = 20
    timeout: float = 120

    def __post_init__(self):
        if self.requests < 1 or self.tokens < 1 or self.tools < 0 or self.timeout <= 0:
            raise ValueError("Execution limits must be positive (tools may be zero)")


class ExecutionPolicy:
    """Revalidate scope first, then enforce budgets, then allow model/tool work.

    Tool-specific object authorization and worker fences remain in their services.
    This policy never grants permission or changes a task's business status.
    """

    def __init__(self, configuration, *, limits=None, validate=None):
        self.configuration = configuration
        self.limits = limits or ExecutionLimits()
        self.validate = validate

    def check_usage(self, usage, *, before=True):
        from app.agents.model import check_usage

        check_usage(
            usage,
            request_limit=self.limits.requests,
            token_limit=self.limits.tokens,
            tool_limit=self.limits.tools,
            before=before,
        )

    async def before_model(self, messages, tools, usage, *, observe_tools=False):
        from app.services.context_budget import ContextBudgetGuard
        from app.services.execution_guard import RepeatedToolResultGuard

        if self.validate:
            await self.validate()
        self.check_usage(usage)
        await ContextBudgetGuard(self.configuration).check(messages, tools)
        if observe_tools:
            RepeatedToolResultGuard().check(messages)

    def after_model(self, response, usage):
        self.check_usage(usage, before=False)
        return self.clarification_first(response)

    @staticmethod
    def clarification_first(response):
        questions = [call for call in response.tool_calls if call["name"] == "ask_user"]
        return (
            response.model_copy(update={"tool_calls": questions[:1], "content": []})
            if questions
            else response
        )

    async def before_tool(self, call, usage, tools):
        if self.validate:
            await self.validate()
        self.check_usage(usage, before=False)
        if call["name"] not in tools:
            raise BadRequestError(message="模型请求了未授权的工具")

    @staticmethod
    def tool_error(exc):
        if isinstance(exc, ToolRetry):
            return str(exc)
        if isinstance(exc, ValidationError):
            return "工具参数与结构定义不符，请修正后重试"
        raise exc
