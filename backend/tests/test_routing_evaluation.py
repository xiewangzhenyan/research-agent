"""Keep abstentions, API failures and wrong upgrades visible in evaluation."""

from unittest.mock import AsyncMock

import pytest

from scripts import evaluate_routing as evaluation


def test_metrics_do_not_count_fallbacks_as_correct_predictions():
    rows = [
        {
            "status": "classified",
            "choice": "standard",
            "recommendation": "standard",
            "expected": "standard",
            "latency_ms": 100,
            "usage": {"input_tokens": 10},
        },
        {
            "status": "classified",
            "choice": "knowledge_collaboration",
            "recommendation": "knowledge_collaboration",
            "expected": "standard",
            "latency_ms": 200,
        },
        {
            "status": "classified",
            "choice": "knowledge_collaboration",
            "recommendation": None,
            "expected": "knowledge_collaboration",
            "latency_ms": 300,
        },
        {
            "status": "unavailable",
            "recommendation": None,
            "expected": "knowledge_collaboration",
            "latency_ms": 2000,
        },
    ]
    result = evaluation.summarize(rows)
    assert result["classified"] == 3
    assert result["raw_choice_accuracy"] == 2 / 3
    assert result["accepted"] == 2
    assert result["accepted_accuracy"] == 0.5
    assert result["fallback_cases"] == 2
    assert result["incorrect_collaboration_upgrades"] == 1
    assert result["missed_collaboration_cases"] == 2
    assert result["median_ms"] == 250
    assert result["p95_ms"] == 2000
    assert result["input_tokens"] == 10


@pytest.mark.anyio
async def test_evaluation_defaults_to_offline_without_service_calls(monkeypatch, capsys):
    classify = AsyncMock()
    monkeypatch.setattr(evaluation, "classify_route", classify)
    monkeypatch.setattr("sys.argv", ["evaluate_routing.py"])
    await evaluation.main()
    classify.assert_not_awaited()
    assert '"mode": "offline"' in capsys.readouterr().out
