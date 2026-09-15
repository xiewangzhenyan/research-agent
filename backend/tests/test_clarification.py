"""Critical versus optional inputs, fixed scopes and bounded model assessment."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.core.exceptions import BadRequestError
from app.services.clarification import (
    SKIP,
    ClarificationFirstGuard,
    ClarificationQuestion,
    answered_items,
    pending_questions,
    supplement,
    validate_answers,
)
from app.services.model_config import resolve_generation_config
from app.services.task_readiness import (
    ReadinessAssessment,
    ReadinessUnavailable,
    assess,
    assess_with_model,
)


def pending(required=True, **extra):
    return pending_questions(
        [{"question": "采用哪个数据集？", "required": required, "allow_custom": True, **extra}],
        kind="readiness",
        round_number=1,
    )


@pytest.mark.parametrize(
    "answer", [SKIP, "不知道", "随便", "用户跳过此问题，请按已有信息继续。", "   "]
)
def test_mandatory_inputs_cannot_be_skipped_even_through_direct_api_payload(answer):
    with pytest.raises(BadRequestError):
        validate_answers(pending(), {"readiness": [answer]})


def test_optional_skip_closed_options_and_question_identity():
    optional = pending(False)
    assert "默认" in answered_items(optional, {"readiness": [SKIP]})[0]["answer"]
    validate_answers(pending(options=["A", "B"], allow_custom=False), {"readiness": ["A"]})
    with pytest.raises(BadRequestError):
        validate_answers(pending(options=["A", "B"], allow_custom=False), {"readiness": ["C"]})
    with pytest.raises(BadRequestError):
        validate_answers(pending(), {"foreign": ["A"]})
    assert (
        pending()["question_id"]
        != pending_questions(pending()["calls"][0]["questions"], kind="readiness", round_number=2)[
            "question_id"
        ]
    )
    with pytest.raises(ValidationError):
        ClarificationQuestion(question="", options=["A"])
    assert ClarificationQuestion(question="数据范围？", allow_custom=False).public()["allow_custom"]


def test_mixed_model_response_defers_all_other_tools_before_dispatch():
    async def check():
        question = ToolCallPart(
            "ask_user", {"questions": [{"question": "数据？"}]}, tool_call_id="q"
        )
        original = ModelResponse(
            parts=[
                ToolCallPart("create_document", {}, tool_call_id="doc"),
                TextPart("开始执行"),
                question,
            ]
        )
        response = await ClarificationFirstGuard().after_model_request(
            None, request_context=None, response=original
        )
        assert response.parts == [question] and len(original.parts) == 3
        other = ModelResponse(parts=[TextPart("直接回答")])
        assert (
            await ClarificationFirstGuard().after_model_request(
                None, request_context=None, response=other
            )
            is other
        )

    asyncio.run(check())


def test_clear_questions_skip_extra_model_call_and_preferences_do_not_block():
    async def check():
        config = resolve_generation_config({})
        with patch(
            "app.services.task_readiness.assess_with_model", new_callable=AsyncMock
        ) as model:
            result, _ = await assess({"prompt": "什么是 LSPR？"}, {}, config, [], {}, AsyncMock())
            assert result["state"] == "ready" and not model.called
            model.return_value = (
                ReadinessAssessment(
                    issues=[ClarificationQuestion(question="用什么语气？", kind="preference")],
                    assumptions=["采用简洁中文"],
                ),
                {},
            )
            result, _ = await assess({"prompt": "生成一份介绍"}, {}, config, [], {}, AsyncMock())
            assert result["state"] == "ready" and not result["questions"]
            assert result["assumptions"] == ["采用简洁中文"]
            model.return_value = (
                ReadinessAssessment(
                    issues=[
                        ClarificationQuestion(
                            question="比较哪两种方案？",
                            kind="ambiguity",
                            reason="对象不同会改变结果",
                            options=["A与B", "A与C"],
                        )
                    ]
                ),
                {},
            )
            result, _ = await assess({"prompt": "比较方案"}, {}, config, [], {}, AsyncMock())
            assert result["state"] == "needs_input" and result["questions"][0]["required"]

    asyncio.run(check())


@pytest.mark.parametrize("controls", [[], ["thinking_effort"]])
def test_real_structured_model_contract_and_fail_closed_without_tools(controls):
    async def check():
        observed = []

        def model(messages, info):
            observed.append(str(messages))
            assert info.function_tools == []
            assert info.model_settings["timeout"] == 40
            assert info.model_settings.get("openai_reasoning_effort") == (
                "low" if controls else None
            )
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        info.output_tools[0].name,
                        {
                            "issues": [
                                {
                                    "question": "范围是哪一个？",
                                    "kind": "ambiguity",
                                    "reason": "两个候选范围不同",
                                    "options": ["甲", "乙"],
                                }
                            ],
                            "assumptions": [],
                        },
                    )
                ]
            )

        validate = AsyncMock()
        with (
            patch("app.services.task_readiness._build_model", return_value=FunctionModel(model)),
            patch("app.services.task_readiness.model_controls", return_value=controls),
        ):
            result, usage = await assess_with_model(
                {
                    "prompt": "比较这些方案",
                    "knowledge_base_ids": ["scoped"],
                    "file_ids": [],
                    "capabilities": [{"kind": "skill"}, {"kind": "mcp"}],
                },
                {"work_context": "不能省略的范围", "history": []},
                resolve_generation_config({}),
                [{"answer": "以前已补充的信息"}],
                {},
                validate,
            )
        assert result.issues[0].kind == "ambiguity" and usage["requests"] == 1
        assert "不能省略的范围" in observed[0] and "以前已补充的信息" in observed[0]
        assert '"bound_capability_kinds": ["skill", "mcp"]' in observed[0]
        validate.assert_awaited_once()
        with (
            patch(
                "app.services.task_readiness.Agent",
                return_value=SimpleNamespace(run=AsyncMock(side_effect=TimeoutError())),
            ),
            patch("app.services.task_readiness._build_model"),
            pytest.raises(ReadinessUnavailable),
        ):
            await assess_with_model(
                {"prompt": "计算数据"}, {}, resolve_generation_config({}), [], {}, validate
            )
        assert "不能充当知识库原文证据" in supplement(
            {"clarification_answers": [{"answer": "用户提供的新说法"}]}
        )

    asyncio.run(check())
