"""Conservative application budgets, distinct from a provider's exact tokenizer."""

import json

from pydantic_ai.capabilities import AbstractCapability

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.services.memory_recall import estimated_tokens

POLICY = "conversation-context-v1"
SYSTEM_RESERVE = 4096


def model_window(model):
    return max(8192, min(262144, settings.AI_MODEL_CONTEXT_LIMITS.get(model, 32768)))


def input_budget(config):
    available = model_window(config.model) - (config.max_output_tokens or 8000) - SYSTEM_RESERVE
    if available < 1024:
        raise BadRequestError(message="当前模型的输出预留过大，请降低回答长度或调整模型上下文配置")
    return min(24000, available)


def cost(value):
    return estimated_tokens(
        value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    )


def check_prompt(prompt, config):
    if cost(prompt) + 512 > input_budget(config):
        raise BadRequestError(message="消息超出当前模型的上下文预算，请分段发送或改为上传文件")


def fit_items(items, tokens):
    chosen, used = [], 0
    for item in items:
        size = cost(item) + 16
        if used + size <= tokens:
            chosen.append(item)
            used += size
    return chosen, used


def envelope(request, config):
    check_prompt(request["prompt"], config)
    available = input_budget(config) - cost(request["prompt"]) - 512
    # Current materials have priority over older conversational background.
    sources = min(6500, max(0, available // 2)) if request.get("knowledge_base_ids") else 0
    files = min(6000, max(0, (available - sources) // 2)) if request.get("file_ids") else 0
    remaining = available - sources - files
    memory = min(1600, remaining // 5)
    recent = min(6000, (remaining - memory) * 2 // 3)
    archive = min(3500, remaining - memory - recent)
    return {
        "input": input_budget(config),
        "sources": sources,
        "files": files,
        "memory": memory,
        "recent": recent,
        "archive": archive,
    }


def request_cost(value):
    """Count text and tool schemas without base64-expanding binary image payloads."""
    from collections.abc import Mapping
    from dataclasses import fields, is_dataclass

    if value is None:
        return 0
    if isinstance(value, bytes):
        return 2000
    if isinstance(value, str):
        return cost(value)
    if isinstance(value, Mapping):
        return 8 + sum(cost(str(k)) + request_cost(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return 8 + sum(request_cost(v) for v in value)
    if is_dataclass(value):
        return 16 + sum(request_cost(getattr(value, f.name)) for f in fields(value))
    return cost(str(value))


class ContextBudgetGuard(AbstractCapability):
    """Check every provider call, including growing tool results and HITL resumes."""

    def __init__(self, config, validate=None):
        self.config, self.validate = config, validate

    async def before_model_request(self, ctx, request_context):
        if self.validate:
            await self.validate()
        estimated = request_cost(request_context.messages) + request_cost(
            request_context.model_request_parameters
        )
        limit = input_budget(self.config) + SYSTEM_RESERVE
        if estimated + 512 > limit:
            raise BadRequestError(message="本轮对话或工具结果已达上下文预算，请拆分任务后继续")
        return request_context
