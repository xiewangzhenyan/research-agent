"""Research scores require exact snapshots and explicit judgments, never self-ratings."""

import copy
import json
import stat
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.schemas.research_evaluation import ResearchDataset, ResearchTrial, TrialReview
from app.services.knowledge_answer import GroundedAnswer, grounded_answer
from app.services.research_evaluation import build_record, evaluate, review_template
from scripts import evaluate_knowledge, evaluate_research


def fixture():
    dataset = ResearchDataset.model_validate(
        {
            "origin": "authored_synthetic",
            "description": "Test only",
            "cases": [
                {
                    "id": "case-one",
                    "split": "development",
                    "question": "审批前可以采购吗？",
                    "requirements": [{"id": "r1", "text": "保留禁止审批前采购的规定"}],
                    "sources": [
                        {
                            "id": "s1",
                            "document_id": "d1",
                            "index": 1,
                            "content": "不得在审批前采购。",
                            "revision": 1,
                        }
                    ],
                }
            ],
        }
    )
    trial = ResearchTrial.model_validate(
        {
            "case_id": "case-one",
            "route": "standard",
            "status": "completed",
            "model": "offline-test",
            "source_ids": ["s1"],
            "answer": {
                "sufficient": True,
                "claims": [
                    {
                        "text": "不得在审批前采购。",
                        "evidence": [{"index": 1, "quote": "不得在审批前采购"}],
                    }
                ],
            },
        }
    )
    return dataset, trial


def reviewed(dataset, trial):
    raw = review_template(build_record(dataset.cases[0], trial))
    raw["reviewer"] = "test-reviewer"
    raw["claims"][0]["support"] = "supported"
    raw["requirements"][0].update(status="satisfied", claim_ids=["c1"])
    return raw


def test_unreviewed_and_unrun_routes_never_receive_confirmed_success():
    dataset, trial = fixture()
    report, packet = evaluate(dataset, [trial], [])
    metrics = report["summary"]["standard"]["development"]
    assert metrics["citation_support_accuracy_reviewed"] is None
    assert metrics["claim_review_coverage"] == 0
    assert metrics["confirmed_success"] == 0
    assert metrics["measured_cost_usd"] is None
    assert metrics["measured_input_tokens"] is None
    assert report["summary"]["knowledge_collaboration"]["development"]["missing_cases"] == 1
    assert packet["reviews"][0]["claims"][0]["support"] is None
    assert packet["records"][0]["sources"][0]["content"] == "不得在审批前采购。"
    assert "不得在审批前采购" not in json.dumps(report, ensure_ascii=False)


def test_reviewed_support_and_requirement_links_are_recorded():
    dataset, trial = fixture()
    # Validate the wire representation, including explicit usage/cost measurements.
    trial = ResearchTrial.model_validate(
        {**trial.model_dump(), "usage": {"input_tokens": 25, "output_tokens": 5}}
    )
    trial.cost_usd = 0.001
    raw = reviewed(dataset, trial)
    report, _ = evaluate(dataset, [trial], [TrialReview.model_validate(raw)])
    metrics = report["summary"]["standard"]["development"]
    assert metrics["confirmed_success"] == 1
    assert metrics["citation_support_accuracy_reviewed"] == 1
    assert metrics["requirement_review_coverage_recorded"] == 1
    assert metrics["measured_input_tokens"] == 25
    assert metrics["measured_cost_usd"] == 0.001
    assert report["rows"][0]["requirement_assessments"][0]["claim_ids"] == ["c1"]


def test_real_quote_can_still_fail_semantic_support_review():
    dataset, trial = fixture()
    trial.answer.claims[0].text = "允许在审批前采购。"
    record = build_record(dataset.cases[0], trial)
    assert record["status"] == "answered"  # Exact quotes do not prove entailment.
    raw = review_template(record)
    raw.update(reviewer="test-reviewer")
    raw["claims"][0]["support"] = "unsupported"
    raw["requirements"][0]["status"] = "missing"
    report, _ = evaluate(dataset, [trial], [TrialReview.model_validate(raw)])
    assert report["rows"][0]["confirmed_success"] is False
    assert report["summary"]["standard"]["development"]["citation_support_accuracy_reviewed"] == 0


@pytest.mark.parametrize("change", ["answer", "source", "revision", "requirement", "model"])
def test_review_is_invalidated_by_snapshot_changes(change):
    dataset, trial = fixture()
    review = TrialReview.model_validate(reviewed(dataset, trial))
    if change == "answer":
        trial.answer.claims[0].text = "采购前须审批。"
    elif change == "source":
        dataset.cases[0].sources[0].content += "新增说明。"
    elif change == "revision":
        dataset.cases[0].sources[0].revision = 2
    elif change == "requirement":
        dataset.cases[0].requirements[0].text += "还需说明原因。"
    else:
        trial.model = "other-model"
    with pytest.raises(ValueError, match="stale"):
        evaluate(dataset, [trial], [review])


@pytest.mark.parametrize(
    "problem",
    [
        "reviewer",
        "duplicate_claim",
        "unknown_claim",
        "duplicate_requirement",
        "unknown_requirement",
        "unknown_link",
        "missing_link",
        "wrong_trial",
    ],
)
def test_invalid_or_unattributed_reviews_are_rejected(problem):
    dataset, trial = fixture()
    raw = reviewed(dataset, trial)
    if problem == "reviewer":
        raw["reviewer"] = "  "
    elif problem == "duplicate_claim":
        raw["claims"] *= 2
    elif problem == "unknown_claim":
        raw["claims"][0]["claim_id"] = "invented"
    elif problem == "duplicate_requirement":
        raw["requirements"] *= 2
    elif problem == "unknown_requirement":
        raw["requirements"][0]["requirement_id"] = "invented"
    elif problem == "unknown_link":
        raw["requirements"][0]["claim_ids"] = ["invented"]
    elif problem == "missing_link":
        raw["requirements"][0]["claim_ids"] = []
    else:
        raw["route"] = "knowledge_collaboration"
    with pytest.raises(ValueError):
        evaluate(dataset, [trial], [TrialReview.model_validate(raw)])


def test_execution_failure_abstention_and_missing_cases_have_separate_denominators():
    dataset, trial = fixture()
    extra = dataset.cases[0].model_copy(deep=True)
    extra.id = "not-run"
    dataset.cases.append(extra)
    failed = trial.model_copy(deep=True)
    failed.status, failed.answer = "timeout", None
    report, _ = evaluate(dataset, [failed], [])
    metrics = report["summary"]["standard"]["development"]
    assert (
        metrics["expected_cases"],
        metrics["errors"],
        metrics["abstained"],
        metrics["missing_cases"],
    ) == (2, 1, 0, 1)
    refused = trial.model_copy(deep=True)
    refused.answer = GroundedAnswer(sufficient=False)
    template = review_template(build_record(dataset.cases[0], refused))
    template.update(reviewer="test-reviewer", abstention="correct")
    template["requirements"][0]["status"] = "satisfied"
    report, _ = evaluate(dataset, [refused], [TrialReview.model_validate(template)])
    assert report["summary"]["standard"]["development"]["confirmed_success_rate"] == 0.5
    template["abstention"] = "uncertain"
    report, _ = evaluate(dataset, [refused], [TrialReview.model_validate(template)])
    assert report["rows"][0]["confirmed_success"] is False


def test_fabricated_quote_is_not_published_or_auto_scored():
    dataset, trial = fixture()
    trial.answer.claims[0].evidence[0].quote = "资料不存在的引文"
    record = build_record(dataset.cases[0], trial)
    assert record["status"] == "abstained" and record["claims"] == []
    assert record["rejected_claims"] == 1


def test_duplicate_trials_and_reviews_and_unknown_source_fail_closed():
    dataset, trial = fixture()
    review = TrialReview.model_validate(reviewed(dataset, trial))
    for trials, reviews in [([trial, trial], []), ([trial], [review, review])]:
        with pytest.raises(ValueError):
            evaluate(dataset, trials, reviews)
    trial.source_ids = ["outside-scope"]
    with pytest.raises(ValueError, match="scope"):
        evaluate(dataset, [trial], [])


@pytest.mark.anyio
async def test_evaluation_capture_is_opt_in_and_reuses_actual_structured_response():
    _, trial = fixture()
    response = SimpleNamespace(
        output=trial.answer, usage={"input_tokens": 12, "output_tokens": 3}, usage_complete=True
    )
    with patch("app.services.knowledge_answer.structured_call", AsyncMock(return_value=response)):
        source = {"index": 1, "content": "不得在审批前采购。"}
        _, _, normal = await grounded_answer("问题", [source], None)
        _, _, captured = await grounded_answer("问题", [source], None, include_evaluation=True)
    assert "evaluation" not in normal
    assert captured["evaluation"]["answer"] == trial.answer.model_dump()
    assert captured["evaluation"]["usage"]["input_tokens"] == 12


@pytest.mark.anyio
@pytest.mark.parametrize("scenario", ["complete", "missing", "retry_missing"])
async def test_native_usage_counters_distinguish_missing_measurements(scenario):
    from app.agents.model import structured_call
    from app.services.model_config import resolve_generation_config
    from tests.model_fixtures import ScriptedModel, model_response, tool_call

    calls = 0

    def respond(messages, info):
        nonlocal calls
        calls += 1
        invalid = scenario == "retry_missing" and calls == 1
        result = model_response(
            [
                tool_call(
                    "GroundedAnswer",
                    {"sufficient": "invalid"} if invalid else {"sufficient": False},
                )
            ]
        )
        if scenario == "missing" or invalid:
            result.usage_metadata = None
        return result

    result = await structured_call(
        ScriptedModel(respond),
        GroundedAnswer,
        "test",
        "test",
        resolve_generation_config({}),
        retries=1,
    )
    assert result.usage_complete is (scenario == "complete")
    with patch("app.services.knowledge_answer.structured_call", AsyncMock(return_value=result)):
        _, _, meta = await grounded_answer(
            "test", [{"index": 1, "content": "test"}], None, include_evaluation=True
        )
    assert (meta["evaluation"]["usage"] is not None) is (scenario == "complete")


@pytest.mark.anyio
async def test_default_cli_only_validates_dataset_without_calls(monkeypatch, capsys):
    live = AsyncMock()
    monkeypatch.setattr(evaluate_research, "run_live", live)
    monkeypatch.setattr("sys.argv", ["evaluate_research.py"])
    await evaluate_research.main()
    live.assert_not_awaited()
    assert '"cases": 10' in capsys.readouterr().out


@pytest.mark.anyio
async def test_offline_replay_round_trip_keeps_private_packets_and_real_scores(
    tmp_path, monkeypatch
):
    dataset, trial = fixture()
    dataset_path, runs_path, reviews_path = [
        tmp_path / f"{name}.json" for name in ("dataset", "runs", "reviews")
    ]
    dataset_path.write_text(dataset.model_dump_json())
    runs_path.write_text(json.dumps({"trials": [trial.model_dump()]}))
    reviews_path.write_text(json.dumps({"reviews": [reviewed(dataset, trial)]}))
    report, packet = tmp_path / "report.json", tmp_path / "packet.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_research.py",
            "--dataset",
            str(dataset_path),
            "--runs",
            str(runs_path),
            "--reviews",
            str(reviews_path),
            "--output",
            str(report),
            "--packet",
            str(packet),
        ],
    )
    await evaluate_research.main()
    value = json.loads(report.read_text())
    assert value["rows"][0]["confirmed_success"] is True
    assert stat.S_IMODE(packet.stat().st_mode) == 0o600
    assert json.loads(reviews_path.read_text())["reviews"][0]["reviewer"] == "test-reviewer"


@pytest.mark.anyio
async def test_cli_does_not_overwrite_review_inputs(tmp_path, monkeypatch):
    path = tmp_path / "keep.json"
    path.write_text("keep")
    monkeypatch.setattr(
        "sys.argv", ["evaluate_research.py", "--runs", str(path), "--output", str(path)]
    )
    with pytest.raises(SystemExit):
        await evaluate_research.main()
    assert path.read_text() == "keep"


@pytest.mark.anyio
async def test_live_failure_does_not_become_an_abstention_or_leak_exception_text():
    dataset, _ = fixture()
    with patch(
        "app.services.knowledge_answer.grounded_answer",
        AsyncMock(side_effect=TimeoutError("private-value")),
    ):
        trials = await evaluate_research.run_live(dataset)
    assert trials[0].status == "timeout"
    assert trials[0].usage is None and trials[0].cost_usd is None
    assert "private-value" not in trials[0].model_dump_json()


@pytest.mark.anyio
async def test_knowledge_report_capture_and_offline_review_preserve_failed_cases(
    tmp_path, monkeypatch
):
    fixture_path = tmp_path / "dataset.json"
    fixture_path.write_text(
        json.dumps(
            {
                "description": "synthetic fixture",
                "documents": [{"id": "d1", "title": "t", "content": "不得在审批前采购。"}],
                "cases": [
                    {
                        "id": "unknown",
                        "split": "development",
                        "question": "未知问题",
                        "expected_document": None,
                    }
                ],
            }
        )
    )
    report_path = tmp_path / "knowledge.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_knowledge.py",
            "--answers",
            "--dataset",
            str(fixture_path),
            "--output",
            str(report_path),
        ],
    )
    monkeypatch.setattr(evaluate_knowledge, "embed", lambda texts: [[1.0] for _ in texts])
    monkeypatch.setattr(
        evaluate_knowledge, "rewrite_query", AsyncMock(return_value=("未知问题", "original"))
    )
    monkeypatch.setattr(
        evaluate_knowledge,
        "rank_chunks",
        lambda *a, **kw: [
            {"index": 1, "document_id": "d1", "content": "不得在审批前采购。", "page": None}
        ],
    )
    monkeypatch.setattr(evaluate_knowledge, "grounded_answer", AsyncMock(side_effect=TimeoutError))
    await evaluate_knowledge.main()
    report = json.loads(report_path.read_text())
    assert report["summary"]["development"]["no_answer_accuracy"] == 0
    assert report["research_trials"][0]["status"] == "timeout"
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_research.py",
            "--knowledge-report",
            str(report_path),
            "--output",
            str(tmp_path / "graded.json"),
            "--packet",
            str(tmp_path / "review.json"),
        ],
    )
    await evaluate_research.main()
    assert json.loads((tmp_path / "graded.json").read_text())["rows"][0]["status"] == "timeout"


def test_dataset_rejects_duplicate_source_indices_and_nonfinite_costs():
    dataset, trial = fixture()
    raw = dataset.model_dump()
    source = copy.deepcopy(raw["cases"][0]["sources"][0])
    source["id"] = "s2"
    raw["cases"][0]["sources"].append(source)
    with pytest.raises(ValidationError):
        ResearchDataset.model_validate(raw)
    with pytest.raises(ValidationError):
        ResearchTrial.model_validate({**trial.model_dump(), "cost_usd": float("nan")})
