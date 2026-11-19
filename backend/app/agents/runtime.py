"""A native LangGraph model/tool subgraph; every tool result is a checkpoint boundary."""

import asyncio
import inspect
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool, create_schema_from_function
from langgraph.graph import END, START, StateGraph

from app.agents.messages import user_content
from app.agents.model import account_usage, provider_options
from app.agents.policy import ExecutionLimits, ExecutionPolicy
from app.agents.policy import ToolRetry as ToolRetry
from app.core.exceptions import BadRequestError


class ToolDeferred(Exception):
    def __init__(self, *, metadata):
        self.metadata = metadata


@dataclass
class ToolContext:
    deps: object


class ToolRegistry:
    """Typed tool registration only; execution belongs to the graph below."""

    def __init__(self, model, configuration, system_prompt="", deps=None):
        self.model, self.configuration, self.system_prompt = model, configuration, system_prompt
        self.deps = deps or SimpleNamespace(allowed_tools=())
        self.tools = {}
        self.instructions = []
        self.limits = ExecutionLimits()

    def register(self, fn=None, *, name=None, context=True):
        def decorate(function):
            tool_name = name or function.__name__
            schema = create_schema_from_function(
                tool_name, function, filter_args=["ctx"] if context else []
            )

            async def execute(**kwargs):
                args = (ToolContext(self.deps),) if context else ()
                value = function(*args, **kwargs)
                return await value if inspect.isawaitable(value) else value

            self.tools[tool_name] = StructuredTool(
                name=tool_name,
                description=inspect.getdoc(function) or tool_name,
                args_schema=schema,
                coroutine=execute,
            )
            return function

        return decorate(fn) if fn else decorate

    def register_plain(self, fn=None, *, name=None):
        return self.register(fn, name=name, context=False)


class RuntimeState(TypedDict, total=False):
    messages: list
    usage: dict
    pending: list
    output: str


def response_text(message):
    return message.text


def reasoning_text(message):
    if not isinstance(message.content, list):
        return ""
    parts = []
    for item in message.content:
        if not isinstance(item, dict) or item.get("type") not in {"reasoning", "reasoning_summary"}:
            continue
        parts.append(item.get("text", ""))
        parts.extend(
            part.get("text", "") for part in item.get("summary", []) if isinstance(part, dict)
        )
    return "".join(parts)


def clarification_first(response):
    return ExecutionPolicy.clarification_first(response)


def build_tool_graph(
    registry,
    *,
    on_event=None,
    validate=None,
    request_limit=None,
    token_limit=None,
    tool_limit=None,
    timeout=None,
):
    defaults = registry.limits
    limits = ExecutionLimits(
        requests=min(request_limit, defaults.requests)
        if request_limit is not None
        else defaults.requests,
        tokens=min(token_limit, defaults.tokens) if token_limit is not None else defaults.tokens,
        tools=min(tool_limit, defaults.tools) if tool_limit is not None else defaults.tools,
        timeout=min(timeout, defaults.timeout) if timeout is not None else defaults.timeout,
    )
    policy = ExecutionPolicy(registry.configuration, limits=limits, validate=validate)

    async def emit(kind, **data):
        if on_event:
            await on_event({"kind": kind, **data})

    async def model_node(state):
        messages = state["messages"]
        usage = state.get("usage", {})
        system = registry.system_prompt + "\n" + "\n".join(registry.instructions)
        inputs = [SystemMessage(content=system), *messages]
        await policy.before_model(inputs, list(registry.tools.values()), usage, observe_tools=True)
        bound = (
            registry.model.bind_tools(
                list(registry.tools.values()),
                **provider_options(registry.configuration.provider_settings()),
            )
            if registry.tools
            else registry.model.bind(**provider_options(registry.configuration.provider_settings()))
        )
        response = None
        async with asyncio.timeout(limits.timeout):
            async for chunk in bound.astream(inputs):
                response = chunk if response is None else response + chunk
                if chunk.text:
                    await emit("text_delta", text=chunk.text)
                thinking = reasoning_text(chunk)
                if thinking:
                    await emit("thinking_delta", text=thinking)
        if response is None:
            raise BadRequestError(message="模型未返回结果")
        if response.invalid_tool_calls:
            raise BadRequestError(message="模型返回了无效的工具调用参数")
        # Chunk parsers accept partial JSON while streaming. Dispatch only after
        # the complete argument string passes strict JSON parsing.
        calls = []
        for call in response.tool_call_chunks:
            try:
                args = json.loads(call["args"])
                if not isinstance(args, dict) or not call["name"] or not call["id"]:
                    raise ValueError("Incomplete tool call")
            except (TypeError, ValueError):
                raise BadRequestError(message="模型返回了无效的工具调用参数") from None
            calls.append({"name": call["name"], "id": call["id"], "args": args})
        # Convert chunks to the stable checkpoint message type.
        response = AIMessage(
            content=response.content,
            tool_calls=calls,
            usage_metadata=response.usage_metadata,
            response_metadata=response.response_metadata,
            additional_kwargs=response.additional_kwargs,
        )
        usage = account_usage(usage, response)
        response = policy.after_model(response, usage)
        return {
            "messages": [*messages, response],
            "usage": usage,
            "pending": [],
            "output": response_text(response),
        }

    def outstanding(state):
        indices = [i for i, m in enumerate(state["messages"]) if isinstance(m, AIMessage)]
        if not indices:
            return []
        index = indices[-1]
        response = state["messages"][index]
        answered = {
            m.tool_call_id for m in state["messages"][index + 1 :] if isinstance(m, ToolMessage)
        }
        return [c for c in response.tool_calls if c["id"] not in answered]

    async def tools_node(state):
        call = outstanding(state)[0]
        usage = dict(state.get("usage", {}))
        usage["tool_calls"] = usage.get("tool_calls", 0) + 1
        await policy.before_tool(call, usage, registry.tools)
        await emit("tool_call", call=call)
        tool = registry.tools.get(call["name"])
        try:
            result = await tool.ainvoke(call["args"])
            content = (
                result
                if isinstance(result, str)
                else json.dumps(result, ensure_ascii=False, default=str)
            )
            status = "success"
        except ToolDeferred as exc:
            return {
                "usage": usage,
                "pending": [{"call_id": call["id"], "tool_name": call["name"], **exc.metadata}],
            }
        except Exception as exc:
            content = policy.tool_error(exc)
            status = "error"
        await emit("tool_result", call=call, content=content)
        return {
            "messages": [
                *state["messages"],
                ToolMessage(
                    content=content, tool_call_id=call["id"], name=call["name"], status=status
                ),
            ],
            "usage": usage,
        }

    graph = StateGraph(RuntimeState)
    graph.add_node("model", model_node)
    graph.add_node("tools", tools_node)
    graph.add_conditional_edges(START, lambda s: "tools" if outstanding(s) else "model")
    graph.add_conditional_edges("model", lambda s: "tools" if outstanding(s) else END)
    graph.add_conditional_edges(
        "tools", lambda s: END if s.get("pending") else "tools" if outstanding(s) else "model"
    )
    return graph.compile()


async def run_tools(registry, prompt, *, history=None, usage=None, replies=None, **kwargs):
    messages = list(history or [])
    if replies:
        names = {
            call["id"]: call["name"]
            for message in messages
            if isinstance(message, AIMessage)
            for call in message.tool_calls
        }
        messages.extend(
            ToolMessage(content=value, tool_call_id=key, name=names.get(key))
            for key, value in replies.items()
        )
    if prompt is not None:
        messages.append(HumanMessage(content=user_content(prompt)))
    return await build_tool_graph(registry, **kwargs).ainvoke(
        {"messages": messages, "usage": usage or {}, "pending": []}, config={"recursion_limit": 100}
    )
