"""Checks that malformed or mismatched evidence cannot become cited answers."""

from unittest.mock import patch

import pytest

from app.services.knowledge_answer import (
    ABSTENTION,
    GroundedAnswer,
    followup_fallback,
    rewrite_query,
    validate_answer,
)

SOURCE = {"index": 1, "content": "住宿每日限额为 650 元，须在 15 个工作日内申请。"}


def answer(text="住宿限额为 650 元。", index=1, quote="住宿每日限额为 650 元"):
    return GroundedAnswer.model_validate(
        {
            "sufficient": True,
            "claims": [{"text": text, "evidence": [{"index": index, "quote": quote}]}],
        }
    )


def test_valid_quote_and_index_render():
    output, sources = validate_answer(answer(), [SOURCE])
    assert "650" in output and "[1]" in output and sources[0]["content"] == SOURCE["content"]
    assert sources[0]["quotes"] == ["住宿每日限额为 650 元"]


@pytest.mark.parametrize(
    "response",
    [
        answer(index=2),
        answer(quote="限额为 999 元"),
        answer(text="可报销 999 元。"),
        answer(text="可报销 65 元。"),
        GroundedAnswer(sufficient=False),
    ],
)
def test_invalid_evidence_abstains(response):
    assert validate_answer(response, [SOURCE]) == (ABSTENTION, [])


def test_no_evidence_or_invented_citation():
    assert validate_answer(answer(), []) == (ABSTENTION, [])
    output, _ = validate_answer(answer(text="限额 650 元。[99]"), [SOURCE])
    assert "[99]" not in output


def test_fallback_preserves_current_constraints_and_avoids_new_topic():
    history = [{"role": "user", "content": "星河项目差旅报销要求"}]
    assert "星河项目" in followup_fallback("那 2026 年需要多久？", history)
    assert "2026" in followup_fallback("那 2026 年需要多久？", history)
    assert followup_fallback("月球实验室的开放时间", history) == "月球实验室的开放时间"


@pytest.mark.anyio
async def test_rewrite_failure_falls_back_without_losing_question():
    with patch("app.services.knowledge_answer.Agent.run", side_effect=TimeoutError):
        query, strategy = await rewrite_query(
            "那申请期限呢？", [{"role": "user", "content": "星河报销"}], None
        )
    assert strategy == "fallback" and "星河" in query and "申请期限" in query


def test_quotes_preserve_original_spacing_and_do_not_mutate_search_hits():
    from app.services.knowledge_answer import source_quote

    content = "🙂测量条件：峰位变化为 12\n nm，范围固定。"
    assert source_quote(content, "峰位变化为12nm") == "峰位变化为 12\n nm"
    source = {"index": 1, "content": content}
    response = answer(text="峰位变化为 12 nm。", quote="峰位变化为12nm")
    _, cited = validate_answer(response, [source])
    assert cited[0]["quotes"] == ["峰位变化为 12\n nm"]
    assert "quotes" not in source
    assert source_quote(content, "   ") is None


def test_multiple_claims_share_one_source_with_distinct_evidence():
    first = answer().model_dump()
    first["claims"].append(
        {"text": "15 个工作日内申请。", "evidence": [{"index": 1, "quote": "15 个工作日内申请"}]}
    )
    output, cited = validate_answer(GroundedAnswer.model_validate(first), [SOURCE])
    assert output.count("[1]") == 2
    assert len(cited) == 1 and len(cited[0]["quotes"]) == 2
