"""Same role graph, explicit publication gate and comparable paired assessments."""

import asyncio
import json
from collections import Counter
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError

from app.schemas.research_evaluation import ResearchTrial, TrialReview
from app.services.knowledge_answer import ABSTENTION
from app.services.model_config import resolve_generation_config
from app.services.research_benchmark import (
    build_source_collaboration_graph,
    run_source_collaboration,
)
from app.services.research_evaluation import build_record, digest, evaluate
from scripts import evaluate_research
from tests.model_fixtures import ScriptedModel, model_response, tool_call
from tests.test_research_evaluation import fixture, reviewed


def model(calls, *, rejection="none", missing_usage=None):
    counts = Counter()

    def respond(messages, info):
        assert not info.function_tools
        schema = info.output_tools[0].name
        role = (
            "planner"
            if schema == "ResearchPlan"
            else "critic"
            if schema == "ReviewResult"
            else "researcher"
            if "证据研究员" in messages[0].content
            else "writer"
        )
        counts[role] += 1
        calls.append(role)
        if role == "planner":
            result = {"objective": "核对条款", "queries": ["采购规定"]}
            if missing_usage == "schema_retry" and counts[role] == 1:
                result = {}
        elif role == "critic":
            rejected = rejection == "always" or (rejection == "once" and counts[role] == 1)
            result = {"approved": not rejected, "issues": ["请复核"] if rejected else []}
        else:
            payload = json.loads(messages[-1].content)
            assert payload["sources"][0]["content"] == "不得在审批前采购。"
            result = {
                "sufficient": True,
                "claims": [
                    {
                        "text": "不得在审批前采购。",
                        "evidence": [
                            {
                                "index": 1,
                                "quote": "不存在的引文"
                                if rejection == "quote" and role == "writer"
                                else "不得在审批前采购",
                            }
                        ],
                    }
                ],
            }
        response = model_response([tool_call(schema, result)])
        if missing_usage == role or (
            missing_usage == "schema_retry" and role == "planner" and counts[role] == 1
        ):
            response.usage_metadata = None
        return response

    return ScriptedModel(respond)


@pytest.mark.anyio
@pytest.mark.parametrize("rejection", ["none", "always", "once", "quote"])
async def test_source_benchmark_uses_real_graph_and_final_publication_decision(rejection):
    dataset, _ = fixture()
    calls = []
    with (
        patch(
            "app.services.knowledge_collaboration._build_model",
            return_value=model(calls, rejection=rejection),
        ),
        patch(
            "app.services.knowledge_collaboration.get_worker_db_context",
            side_effect=AssertionError("No DB in fixed-source benchmark"),
        ),
    ):
        detail = await run_source_collaboration(dataset.cases[0], resolve_generation_config({}))
    approved = rejection in {"none", "once"}
    assert detail["collaboration"]["approved"] is approved
    assert detail["collaboration"]["revisions"] == (0 if rejection == "none" else 1)
    assert Counter(calls)["planner"] == Counter(calls)["researcher"] == 1
    assert Counter(calls)["writer"] == (1 if rejection == "none" else 2)
    assert detail["usage"] == {"input_tokens": len(calls), "output_tokens": len(calls)}
    trial = ResearchTrial.model_validate(
        {
            "case_id": dataset.cases[0].id,
            "route": "knowledge_collaboration",
            "status": "completed",
            "model": "test",
            "source_ids": ["s1"],
            **detail,
        }
    )
    record = build_record(dataset.cases[0], trial)
    assert (record["status"] == "answered") is approved
    if not approved:
        assert record["output"] == ABSTENTION and record["claims"] == []
        assert record["rejected_claims"] == 1
    report, _ = evaluate(dataset, [trial], [])
    assert report["rows"][0]["confirmed_success"] is False  # A critic is not a human review.


@pytest.mark.anyio
@pytest.mark.parametrize("missing", ["researcher", "critic", "schema_retry"])
async def test_missing_usage_stays_unknown_across_roles_and_schema_retries(missing):
    dataset, _ = fixture()
    with patch(
        "app.services.knowledge_collaboration._build_model",
        return_value=model([], missing_usage=missing),
    ):
        detail = await run_source_collaboration(dataset.cases[0], resolve_generation_config({}))
    assert detail["usage"] is None


@pytest.mark.anyio
async def test_empty_source_benchmark_skips_research_writer_and_critic():
    dataset, _ = fixture()
    dataset.cases[0].sources = []
    calls = []
    with patch("app.services.knowledge_collaboration._build_model", return_value=model(calls)):
        detail = await run_source_collaboration(dataset.cases[0], resolve_generation_config({}))
    assert calls == ["planner"]
    assert detail["answer"]["sufficient"] is False
    assert detail["collaboration"]["approved"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("changed_scope", [False, True])
async def test_shared_graph_recovery_reuses_completed_roles_and_checks_source_snapshot(
    changed_scope,
):
    from app.services import knowledge_collaboration

    dataset, _ = fixture()
    case = dataset.cases[0]
    saver, calls = InMemorySaver(), []
    config = resolve_generation_config({}).model_dump()
    checkpoint = {"configurable": {"thread_id": str(uuid4())}}
    original, fail = knowledge_collaboration.run_role, True

    async def invoke(role, *args, **kwargs):
        nonlocal fail
        if role == "writer" and fail:
            fail = False
            raise RuntimeError("Interrupted")
        return await original(role, *args, **kwargs)

    with (
        patch.object(knowledge_collaboration, "run_role", side_effect=invoke),
        patch.object(knowledge_collaboration, "_build_model", return_value=model(calls)),
    ):
        graph = build_source_collaboration_graph(case, config, checkpointer=saver)
        with pytest.raises(RuntimeError):
            await graph.ainvoke({"prompt": case.question, "base_ids": []}, checkpoint)
        if changed_scope:
            case.sources[0].content = "不同的资料。"
        rebuilt = build_source_collaboration_graph(case, config, checkpointer=saver)
        if changed_scope:
            with pytest.raises(ValueError, match="snapshot"):
                await rebuilt.ainvoke(None, checkpoint)
            assert calls == ["planner", "researcher"]
        else:
            result = await rebuilt.ainvoke(None, checkpoint)
            assert result["citations"]
            assert calls == ["planner", "researcher", "writer", "critic"]


@pytest.mark.anyio
async def test_fixed_source_adapter_rejects_database_scope_before_any_model_call():
    dataset, _ = fixture()
    factory = AsyncMock()
    graph = build_source_collaboration_graph(
        dataset.cases[0], resolve_generation_config({}).model_dump()
    )
    with (
        patch("app.services.knowledge_collaboration.run_role", factory),
        pytest.raises(ValueError, match="scope"),
    ):
        await graph.ainvoke({"prompt": dataset.cases[0].question, "base_ids": [str(uuid4())]})
    factory.assert_not_awaited()


def paired_trials():
    dataset, standard = fixture()
    standard.configuration_sha256 = "a" * 64
    collaboration = ResearchTrial.model_validate(
        {
            **standard.model_dump(),
            "route": "knowledge_collaboration",
            "collaboration": {
                "version": "knowledge-collaboration-v1",
                "approved": True,
                "revisions": 0,
            },
        }
    )
    return dataset, standard, collaboration


def test_paired_wins_require_reviews_and_matching_model_input_and_configuration():
    dataset, standard, collaboration = paired_trials()
    report, _ = evaluate(dataset, [standard, collaboration], [])
    comparison = report["paired_comparison"]["development"]
    assert comparison["comparable_pairs"] == comparison["pending_review_pairs"] == 1
    assert comparison["both_successful"] == comparison["reviewed_pairs"] == 0
    reviews = [
        TrialReview.model_validate(reviewed(dataset, trial)) for trial in (standard, collaboration)
    ]
    report, _ = evaluate(dataset, [standard, collaboration], reviews)
    assert report["paired_comparison"]["development"]["both_successful"] == 1


@pytest.mark.parametrize(
    "mismatch,field",
    [
        ("model", "model_mismatch_pairs"),
        ("config", "unknown_or_mismatched_configuration_pairs"),
        ("sources", "source_mismatch_pairs"),
    ],
)
def test_incomparable_pairs_are_not_treated_as_route_wins(mismatch, field):
    dataset, standard, collaboration = paired_trials()
    if mismatch == "model":
        collaboration.model = "other-model"
    elif mismatch == "config":
        collaboration.configuration_sha256 = None
    else:
        collaboration.source_ids = []
    report, _ = evaluate(dataset, [standard, collaboration], [])
    comparison = report["paired_comparison"]["development"]
    assert comparison[field] == 1
    assert comparison["comparable_pairs"] == comparison["reviewed_pairs"] == 0


def test_failed_peer_is_a_known_failure_but_never_a_reviewed_abstention():
    dataset, standard, collaboration = paired_trials()
    collaboration.status, collaboration.answer, collaboration.collaboration = "timeout", None, None
    report, _ = evaluate(
        dataset,
        [standard, collaboration],
        [TrialReview.model_validate(reviewed(dataset, standard))],
    )
    comparison = report["paired_comparison"]["development"]
    assert comparison["standard_only_successful"] == 1
    assert report["summary"]["knowledge_collaboration"]["development"]["abstained"] == 0


def test_uncertain_review_is_not_a_decisive_paired_loss():
    dataset, standard, collaboration = paired_trials()
    uncertain = reviewed(dataset, collaboration)
    uncertain["claims"][0]["support"] = "uncertain"
    uncertain["requirements"][0].update(status="uncertain", claim_ids=[])
    reviews = [
        TrialReview.model_validate(reviewed(dataset, standard)),
        TrialReview.model_validate(uncertain),
    ]
    report, _ = evaluate(dataset, [standard, collaboration], reviews)
    comparison = report["paired_comparison"]["development"]
    assert comparison["pending_review_pairs"] == 1
    assert comparison["standard_only_successful"] == comparison["reviewed_pairs"] == 0


def test_legacy_standard_fingerprint_stays_stable_and_collaboration_requires_approval_record():
    dataset, trial = fixture()
    legacy = trial.model_dump(exclude={"collaboration", "configuration_sha256"})
    assert build_record(dataset.cases[0], trial)["fingerprint"] == digest(
        {"case": dataset.cases[0].model_dump(), "trial": legacy}
    )
    with pytest.raises(ValidationError, match="publication"):
        ResearchTrial.model_validate({**legacy, "route": "knowledge_collaboration"})


@pytest.mark.anyio
async def test_live_both_alternates_order_and_keeps_identical_fresh_inputs():
    dataset, trial = fixture()
    second = dataset.cases[0].model_copy(deep=True)
    second.id = "second-case"
    dataset.cases.append(second)
    order = []

    async def standard(question, sources, *args, **kwargs):
        order.append(("standard", sources))
        return "text", [], {"evaluation": {"answer": trial.answer.model_dump(), "usage": None}}

    async def collaboration(case, config):
        order.append(("knowledge_collaboration", [s.model_dump() for s in case.sources]))
        return {
            "answer": trial.answer.model_dump(),
            "usage": None,
            "collaboration": {
                "version": "knowledge-collaboration-v1",
                "approved": True,
                "revisions": 0,
            },
        }

    with (
        patch("app.services.knowledge_answer.grounded_answer", side_effect=standard),
        patch(
            "app.services.research_benchmark.run_source_collaboration", side_effect=collaboration
        ),
    ):
        trials = await evaluate_research.run_live(
            dataset, routes=("standard", "knowledge_collaboration")
        )
    assert [r for r, _ in order] == [
        "standard",
        "knowledge_collaboration",
        "knowledge_collaboration",
        "standard",
    ]
    assert all(sources == order[0][1] for _, sources in order)
    assert len(trials) == 4 and len({t.configuration_sha256 for t in trials}) == 1


@pytest.mark.anyio
async def test_cli_keeps_completed_trial_if_next_route_is_interrupted(tmp_path, monkeypatch):
    dataset, trial = fixture()
    dataset_path, runs = tmp_path / "cases.json", tmp_path / "runs.json"
    dataset_path.write_text(dataset.model_dump_json())
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_research.py",
            "--live",
            "--route",
            "both",
            "--dataset",
            str(dataset_path),
            "--save-runs",
            str(runs),
            "--output",
            str(tmp_path / "report.json"),
            "--packet",
            str(tmp_path / "packet.json"),
        ],
    )
    with (
        patch(
            "app.services.knowledge_answer.grounded_answer",
            AsyncMock(
                return_value=(
                    "text",
                    [],
                    {"evaluation": {"answer": trial.answer.model_dump(), "usage": None}},
                )
            ),
        ),
        patch(
            "app.services.research_benchmark.run_source_collaboration",
            AsyncMock(side_effect=asyncio.CancelledError),
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await evaluate_research.main()
    captured = json.loads(runs.read_text())
    assert captured["dataset_sha256"] == digest(dataset.model_dump())
    assert len(captured["trials"]) == 1 and captured["trials"][0]["route"] == "standard"
    assert not (tmp_path / "report.json").exists()


@pytest.mark.anyio
async def test_cli_rejects_a_snapshot_from_another_dataset_revision(tmp_path, monkeypatch):
    dataset, trial = fixture()
    cases, runs = tmp_path / "cases.json", tmp_path / "runs.json"
    cases.write_text(dataset.model_dump_json())
    runs.write_text(json.dumps({"dataset_sha256": "0" * 64, "trials": [trial.model_dump()]}))
    output = tmp_path / "report.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_research.py",
            "--dataset",
            str(cases),
            "--runs",
            str(runs),
            "--output",
            str(output),
            "--packet",
            str(tmp_path / "packet.json"),
        ],
    )
    with pytest.raises(SystemExit):
        await evaluate_research.main()
    assert not output.exists()
