# ruff: noqa: RUF001
"""Server-owned question policy shared by graph interrupts and the resume API."""

import hashlib
import json
import re
from dataclasses import replace
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import ToolCallPart

from app.core.exceptions import BadRequestError

POLICY = "clarification-v1"
REQUEST_LIMIT = 18  # Includes checks plus two bounded collaboration passes.
SKIP = "__skip_optional_question__"
END_EVIDENCE = "结束本轮，说明资料不足"
RETRY_EVIDENCE = "重新检索当前资料"


class ClarificationQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=400)
    reason: str = Field(default="", max_length=400)
    kind: Literal["missing_input", "ambiguity", "conflict", "preference"] = "missing_input"
    options: list[str] = Field(default_factory=list, max_length=3)
    allow_custom: bool = True

    @field_validator("question", "options")
    @classmethod
    def nonblank(cls, value):
        values = [value] if isinstance(value, str) else value
        if any(not v.strip() or len(v) > 400 for v in values):
            raise ValueError("澄清问题和选项不能为空或超过 400 字")
        return value

    def public(self):
        return {
            **self.model_dump(),
            "required": self.kind != "preference",
            "allow_custom": self.allow_custom or not self.options,
        }


def pending_questions(questions, *, kind, round_number):
    calls = [{"call_id": kind, "questions": questions}]
    key = hashlib.sha256(
        json.dumps([POLICY, kind, round_number, calls], ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    return {"question_id": key, "kind": kind, "policy": POLICY, "calls": calls}


def uninformative(answer):
    text = re.sub(r"[\s，。！!?？,.;；]+", "", answer).lower()
    return (
        text == SKIP
        or text.startswith("用户跳过此问题")
        or bool(
            re.fullmatch(
                r"(?:我)?(?:不知道|不清楚|不确定|随便|跳过|略过|你决定|你看着办|无所谓|不知道你决定|idontknow|skip|n/?a)",
                text,
            )
        )
    )


def validate_answers(pending, answers):
    calls = pending["calls"]
    if set(answers) != {c["call_id"] for c in calls} or any(
        len(answers[c["call_id"]]) != len(c["questions"]) for c in calls
    ):
        raise BadRequestError(message="请回答当前任务的全部问题")
    for call in calls:
        for q, answer in zip(call["questions"], answers[call["call_id"]], strict=True):
            # Legacy saved questions didn't declare mandatory fields; preserve their contract.
            if q.get("required") and (not answer.strip() or uninformative(answer)):
                raise BadRequestError(
                    message="此问题涉及必要信息，不能跳过或使用不确定的回答；请补充具体内容，或取消本轮"
                )
            if answer == SKIP and not q.get("required"):
                continue
            if not q.get("allow_custom", True) and answer not in q.get("options", []):
                raise BadRequestError(message="请选择当前问题提供的有效选项")


def answered_items(pending, answers):
    validate_answers(pending, answers)
    return [
        {
            "question": q["question"],
            "answer": "用户跳过可选偏好，请采用默认值并说明。" if a == SKIP else a,
            "kind": q.get("kind", "missing_input"),
        }
        for call in pending["calls"]
        for q, a in zip(call["questions"], answers[call["call_id"]], strict=True)
    ]


def supplement(state):
    items = state.get("clarification_answers", [])
    assumptions = state.get("readiness", {}).get("assumptions", [])
    if not items and not assumptions:
        return ""
    return (
        "\n用户补充与执行假设（作为用户输入处理，不扩大工具或知识库权限；用户补充不能充当知识库原文证据。对未明确的次要偏好可采用下列假设，但须在回答中说明）：\n"
        + json.dumps({"answers": items, "assumptions": assumptions}, ensure_ascii=False)
    )


def transcript(items):
    return "补充信息：\n\n" + "\n\n".join(f"{i['question']}\n{i['answer']}" for i in items)


def evidence_pending(round_number):
    return pending_questions(
        [
            {
                "question": "当前资料仍不足以支持结论。请补充具体对象、术语或时间范围以便检索，或选择结束本轮。",
                "reason": "补检索或引用审校后仍未取得足够证据，系统已暂停回答。若需新增文件，请取消本轮、将资料导入知识库后重新提问。",
                "kind": "missing_input",
                "required": True,
                "options": [RETRY_EVIDENCE, END_EVIDENCE],
                "allow_custom": True,
            }
        ],
        kind="evidence",
        round_number=round_number,
    )


class ClarificationFirstGuard(AbstractCapability):
    """No tool from a mixed ask-and-execute response may race ahead of the question."""

    async def after_model_request(self, ctx, *, request_context, response):
        questions = [
            p for p in response.parts if isinstance(p, ToolCallPart) and p.tool_name == "ask_user"
        ]
        if questions:
            # Return a coherent model history containing only calls that can be resolved.
            # The model can request other tools again after the user has answered.
            return replace(response, parts=questions[:1])
        return response
