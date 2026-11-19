"""Stop repeated tool results without a second scheduler or mutable global state."""

import hashlib
import json
from collections import Counter, deque

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.exceptions import BadRequestError


class ExecutionStalledError(BadRequestError):
    message = "工具反复返回相同结果，本轮已停止以避免重复消耗；请调整问题或补充资料后继续"
    code = "EXECUTION_STALLED"


class RepeatedToolResultGuard:
    """Rebuild from persisted messages, so HITL/checkpoint resumes retain the guard.

    Three identical (tool, arguments, result) observations within the last twelve
    results stop the next model call. Different results count as progress. A new
    user message or an answered clarification starts a fresh observation window.
    """

    def check(self, messages):
        calls = {}
        recent = deque(maxlen=12)
        for message in messages:
            if isinstance(message, HumanMessage):
                calls.clear()
                recent.clear()
            elif isinstance(message, AIMessage):
                calls.update({call["id"]: call for call in message.tool_calls})
            elif isinstance(message, ToolMessage):
                if message.name == "ask_user":
                    calls.clear()
                    recent.clear()
                    continue
                call = calls.pop(message.tool_call_id, None)
                if call is None:
                    continue
                fingerprint = hashlib.sha256(
                    json.dumps(
                        [call["name"], call["args"], message.content],
                        sort_keys=True,
                        ensure_ascii=False,
                        default=str,
                    ).encode()
                ).digest()
                recent.append(fingerprint)
        if any(count >= 3 for count in Counter(recent).values()):
            raise ExecutionStalledError()
