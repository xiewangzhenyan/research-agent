"""Native LangChain messages and a read-only decoder for pre-migration checkpoints."""

import base64
import json

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    messages_from_dict,
    messages_to_dict,
)


def image_content(data: bytes, media_type: str) -> dict:
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{media_type};base64,{base64.b64encode(data).decode()}"},
    }


def user_content(value):
    if isinstance(value, str):
        return value
    return [{"type": "text", "text": part} if isinstance(part, str) else part for part in value]


def history_messages(history):
    classes = {"user": HumanMessage, "assistant": AIMessage, "system": SystemMessage}
    return [classes[m["role"]](content=m["content"]) for m in history or [] if m["role"] in classes]


def dump_messages(messages):
    return json.dumps(messages_to_dict(messages), ensure_ascii=False)


def load_messages(value):
    if not value:
        return []
    rows = json.loads(value) if isinstance(value, str) else value
    if not rows or "type" in rows[0]:
        return messages_from_dict(rows)
    messages = []
    for row in rows:
        text, calls = [], []
        for part in row.get("parts", []):
            kind = part.get("part_kind")
            if kind == "system-prompt":
                messages.append(SystemMessage(content=part["content"]))
            elif kind == "user-prompt":
                content = part["content"]
                if isinstance(content, list):
                    converted = []
                    for item in content:
                        if isinstance(item, str):
                            converted.append({"type": "text", "text": item})
                        elif isinstance(item, dict) and item.get("kind") == "binary":
                            converted.append(
                                image_content(base64.b64decode(item["data"]), item["media_type"])
                            )
                        else:
                            raise ValueError("Unsupported legacy multimodal checkpoint")
                    content = converted
                messages.append(HumanMessage(content=content))
            elif kind in ("text", "thinking"):
                if kind == "text":
                    text.append(part.get("content", ""))
            elif kind == "tool-call":
                args = part.get("args") or {}
                calls.append(
                    {
                        "name": part["tool_name"],
                        "args": json.loads(args) if isinstance(args, str) else args,
                        "id": part["tool_call_id"],
                    }
                )
            elif kind in ("tool-return", "retry-prompt"):
                content = part.get("content", "")
                if part.get("tool_call_id"):
                    messages.append(
                        ToolMessage(
                            content=content
                            if isinstance(content, str)
                            else json.dumps(content, ensure_ascii=False),
                            tool_call_id=part["tool_call_id"],
                            name=part.get("tool_name"),
                            status="error" if kind == "retry-prompt" else "success",
                        )
                    )
                else:
                    messages.append(HumanMessage(content=str(content)))
            else:
                raise ValueError("Unsupported legacy checkpoint part")
        if row.get("kind") == "response":
            messages.append(AIMessage(content="".join(text), tool_calls=calls))
    return messages
