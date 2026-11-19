"""Single Responses transport and bounded structured model calls."""

import asyncio
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import BadRequestError, RateLimitError


def build_model(name):
    return ChatOpenAI(
        model=name or settings.AI_MODEL,
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        use_responses_api=True,
        output_version="responses/v1",
        max_retries=0,
    )


def provider_options(options):
    values = dict(options)
    effort = values.pop("openai_reasoning_effort", None)
    summary = values.pop("openai_reasoning_summary", None)
    if effort:
        values["reasoning"] = {"effort": effort, **({"summary": summary} if summary else {})}
    # The overall deadline is enforced locally, not sent as a model parameter.
    values.pop("timeout", None)
    return values


def account_usage(usage, message, *, requests=1, tool_calls=0):
    result = dict(usage or {})
    actual = message.usage_metadata or {}
    for key, delta in {
        "requests": requests,
        "tool_calls": tool_calls,
        "input_tokens": actual.get("input_tokens", 0),
        "output_tokens": actual.get("output_tokens", 0),
    }.items():
        result[key] = result.get(key, 0) + delta
    return result


def check_usage(usage, *, request_limit=12, token_limit=60000, tool_limit=20, before=True):
    requests = usage.get("requests", 0)
    if requests > request_limit or (before and requests == request_limit):
        raise RateLimitError(message="本轮模型调用已达上限，请拆分任务后继续")
    if (
        usage.get("tool_calls", 0) > tool_limit
        or usage.get("input_tokens", 0) + usage.get("output_tokens", 0) > token_limit
    ):
        raise RateLimitError(message="本轮执行已达用量上限，请拆分任务后继续")


@dataclass
class StructuredResult:
    output: object
    usage: dict
    usage_complete: bool = False


async def structured_call(
    model,
    schema,
    system_prompt,
    prompt,
    configuration,
    *,
    usage=None,
    request_limit=12,
    token_limit=60000,
    retries=0,
    model_settings=None,
    validate=None,
):
    from app.agents.policy import ExecutionLimits, ExecutionPolicy

    options = {**configuration.provider_settings(), **(model_settings or {})}
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=prompt)]
    bound = model.bind_tools([schema], tool_choice=schema.__name__, **provider_options(options))
    current = dict(usage or {})
    usage_complete = not usage or usage.get("usage_complete", usage.get("requests", 0) == 0) is True
    policy = ExecutionPolicy(
        configuration,
        limits=ExecutionLimits(
            requests=request_limit, tokens=token_limit, timeout=options.get("timeout", 90)
        ),
        validate=validate,
    )
    for attempt in range(retries + 1):
        await policy.before_model(messages, [schema.model_json_schema()], current)
        async with asyncio.timeout(options.get("timeout", 90)):
            response = await bound.ainvoke(messages)
        current = account_usage(current, response)
        reported = response.usage_metadata or {}
        usage_complete = usage_complete and all(
            type(reported.get(key)) is int for key in ("input_tokens", "output_tokens")
        )
        if "usage_complete" in current:
            current["usage_complete"] = usage_complete
        policy.check_usage(current, before=False)
        try:
            if len(response.tool_calls) != 1 or response.tool_calls[0]["name"] != schema.__name__:
                raise ValueError("Expected one structured result")
            return StructuredResult(
                schema.model_validate(response.tool_calls[0]["args"]),
                current,
                usage_complete=usage_complete,
            )
        except (ValidationError, ValueError):
            if attempt == retries:
                raise BadRequestError(message="模型未返回符合要求的结构化结果") from None
            # Retry a pure classification/generation call only; no tools execute here.
            messages.append(
                HumanMessage(
                    content="Return one valid result matching the supplied schema. Do not execute tools."
                )
            )
    raise AssertionError("unreachable")
