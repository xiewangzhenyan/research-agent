"""Deterministic native LangChain chat models for unit and database workflow tests."""

import inspect
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool


def tool_call(tool_name, args, tool_call_id=None):
    return {
        "name": tool_name,
        "args": args,
        "id": tool_call_id or str(uuid4()),
        "type": "tool_call",
    }


def text_part(content):
    return content


def model_response(parts):
    return AIMessage(
        content="".join(p for p in parts if isinstance(p, str)),
        tool_calls=[p for p in parts if isinstance(p, dict)],
        usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
    )


def tool_delta(*, name=None, json_args=None, tool_call_id=None):
    return {"name": name, "args": json_args, "id": tool_call_id}


class ScriptedModel(BaseChatModel):
    function: Any = None
    stream_function: Any = None
    tools: list = []
    is_structured: bool = False

    def __init__(self, function=None, *, stream_function=None, **kwargs):
        super().__init__(function=function, stream_function=stream_function, **kwargs)

    @property
    def _llm_type(self):
        return "scripted-test-model"

    def bind_tools(self, tools, **kwargs):
        output = any(isinstance(t, type) for t in tools)
        clone = self.model_copy(
            update={
                "tools": [convert_to_openai_tool(t)["function"] for t in tools],
                "is_structured": output,
            }
        )
        return clone.bind(**kwargs)

    def info(self, kwargs):
        items = [
            SimpleNamespace(name=t["name"], parameters_json_schema=t["parameters"])
            for t in self.tools
        ]
        options = dict(kwargs)
        if options.get("reasoning"):
            options["openai_reasoning_effort"] = options["reasoning"]["effort"]
        return SimpleNamespace(
            function_tools=[] if self.is_structured else items,
            output_tools=items if self.is_structured else [],
            model_settings=options,
        )

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.function is None:
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="test response"))]
            )
        return ChatResult(
            generations=[ChatGeneration(message=self.function(messages, self.info(kwargs)))]
        )

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.function is not None:
            result = self.function(messages, self.info(kwargs))
            if inspect.isawaitable(result):
                result = await result
            return ChatResult(generations=[ChatGeneration(message=result)])
        response = None
        async for chunk in self._astream(messages, **kwargs):
            response = chunk.message if response is None else response + chunk.message
        return ChatResult(
            generations=[ChatGeneration(message=response or AIMessage(content="test response"))]
        )

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        if self.stream_function is None:
            response = (
                (await self._agenerate(messages, **kwargs)).generations[0].message
                if self.function
                else AIMessage(content="test response")
            )
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=response.content,
                    tool_calls=response.tool_calls,
                    usage_metadata=response.usage_metadata,
                )
            )
            return
        async for item in self.stream_function(messages, self.info(kwargs)):
            if isinstance(item, str):
                message = AIMessageChunk(content=item)
            else:
                message = AIMessageChunk(
                    content="", tool_call_chunks=[{**v, "index": i} for i, v in item.items()]
                )
            yield ChatGenerationChunk(message=message)
