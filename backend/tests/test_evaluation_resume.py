"""Paid batch continuation must preserve results, failure history and real costs."""

import json
import stat
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.research_evaluation import ResearchSnapshot, ResearchTrial
from app.services.model_config import resolve_generation_config
from app.services.research_evaluation import digest, evaluate
from app.services.research_evaluation_runs import pipeline_fingerprint, validate_attempts
from scripts import evaluate_research
from tests.test_research_evaluation import fixture


def saved_batch(*, status="completed", route="standard", routes=None):
    dataset, base = fixture()
    config = resolve_generation_config({})
    data = {
        **base.model_dump(),
        "model": config.model,
        "configuration_sha256": digest(config.model_dump()),
        "route": route,
        "status": status,
    }
    if status != "completed":
        data.update(answer=None, latency_ms=7, error_type="TimeoutError")
    elif route == "knowledge_collaboration":
        data["collaboration"] = {
            "version": "knowledge-collaboration-v1",
            "approved": False,
            "revisions": 1,
        }
    trial = ResearchTrial.model_validate(data)
    return dataset, ResearchSnapshot.model_validate(
        {
            "version": "research-run-snapshot-v1",
            "dataset_sha256": digest(dataset.model_dump()),
            "configuration_sha256": digest(config.model_dump()),
            "pipeline_sha256": pipeline_fingerprint(),
            "model": config.model,
            "routes": list(routes or (route,)),
            "trials": [trial],
            "attempts": [trial],
        }
    )


def standard_result(answer):
    return (
        "result",
        [],
        {
            "evaluation": {
                "answer": answer.model_dump(),
                "usage": {"input_tokens": 2, "output_tokens": 1},
            }
        },
    )


def collaboration_result(answer):
    return {
        "answer": answer.model_dump(),
        "usage": {"input_tokens": 4, "output_tokens": 2},
        "collaboration": {
            "version": "knowledge-collaboration-v1",
            "approved": True,
            "revisions": 0,
        },
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status,route",
    [
        ("completed", "standard"),
        ("error", "standard"),
        ("timeout", "standard"),
        ("completed", "knowledge_collaboration"),
    ],
)
async def test_default_resume_retains_every_recorded_outcome_without_calls(status, route):
    dataset, saved = saved_batch(status=status, route=route)
    original = saved.model_dump()
    with (
        patch("app.services.knowledge_answer.grounded_answer", AsyncMock()) as standard,
        patch(
            "app.services.research_benchmark.run_source_collaboration", AsyncMock()
        ) as collaboration,
    ):
        result = await evaluate_research.run_live(dataset, routes=(route,), resume=saved)
    standard.assert_not_awaited()
    collaboration.assert_not_awaited()
    assert result[0].status == status and saved.model_dump() == original


@pytest.mark.anyio
async def test_partial_two_route_resume_executes_only_missing_route():
    dataset, saved = saved_batch(routes=("standard", "knowledge_collaboration"))
    retained = saved.trials[0].model_dump()
    checkpoints = []

    async def capture(snapshot):
        checkpoints.append(snapshot)

    with (
        patch("app.services.knowledge_answer.grounded_answer", AsyncMock()) as standard,
        patch(
            "app.services.research_benchmark.run_source_collaboration",
            AsyncMock(return_value=collaboration_result(saved.trials[0].answer)),
        ) as collaboration,
    ):
        result = await evaluate_research.run_live(
            dataset, routes=tuple(saved.routes), resume=saved, on_checkpoint=capture
        )
    standard.assert_not_awaited()
    collaboration.assert_awaited_once()
    assert len(checkpoints[-1].attempts) == 2 and result[0].model_dump() == retained
    assert len(saved.trials) == 1  # Caller-owned input is not changed.


@pytest.mark.anyio
@pytest.mark.parametrize("still_failing", [False, True])
async def test_explicit_retry_attempts_a_failure_once_and_keeps_history(still_failing):
    dataset, saved = saved_batch(status="timeout")
    _, answer = fixture()
    checkpoints = []

    async def capture(snapshot):
        checkpoints.append(snapshot)

    response = (
        AsyncMock(side_effect=TimeoutError)
        if still_failing
        else AsyncMock(return_value=standard_result(answer.answer))
    )
    with patch("app.services.knowledge_answer.grounded_answer", response):
        result = await evaluate_research.run_live(
            dataset, resume=saved, retry_failed=True, on_checkpoint=capture
        )
    response.assert_awaited_once()
    final = checkpoints[-1]
    assert len(final.attempts) == 2 and final.attempts[0].status == "timeout"
    assert len(final.trials) == 1 and final.trials[0].status == (
        "timeout" if still_failing else "completed"
    )
    report, _ = evaluate(dataset, result, [], attempts=final.attempts)
    totals = report["attempt_summary"]["standard"]["development"]
    assert totals["recorded_attempts"] == 2 and totals["retried_cases"] == 1
    assert totals["failed_attempts"] == (2 if still_failing else 1)
    assert totals["total_latency_ms"] == 7 + result[0].latency_ms
    assert totals["total_input_tokens"] is None  # The timed-out attempt did not report usage.
    assert totals["completed_after_retry_cases"] == (0 if still_failing else 1)


@pytest.mark.anyio
@pytest.mark.parametrize("abstained", [False, True])
async def test_retry_failed_never_reruns_completed_answers_or_refusals(abstained):
    dataset, saved = saved_batch()
    if abstained:
        saved.trials[0].answer.sufficient = False
    with patch("app.services.knowledge_answer.grounded_answer", AsyncMock()) as generate:
        await evaluate_research.run_live(dataset, resume=saved, retry_failed=True)
    generate.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mismatch",
    [
        "dataset",
        "model",
        "configuration",
        "pipeline",
        "routes",
        "source_scope",
        "trial_model",
        "duplicate",
        "ledger",
        "legacy",
    ],
)
async def test_bad_resume_is_rejected_before_checkpoint_writes_or_model_calls(mismatch):
    dataset, saved = saved_batch()
    if mismatch == "dataset":
        dataset.cases[0].question += "新要求"
    elif mismatch == "model":
        saved.model = "different-model"
    elif mismatch == "configuration":
        saved.configuration_sha256 = "b" * 64
    elif mismatch == "pipeline":
        saved.pipeline_sha256 = "b" * 64
    elif mismatch == "routes":
        saved.routes = ["standard", "knowledge_collaboration"]
    elif mismatch == "source_scope":
        saved.trials[0].source_ids = []
    elif mismatch == "trial_model":
        saved.trials[0].model = "different-model"
    elif mismatch == "duplicate":
        saved.trials.append(saved.trials[0])
    elif mismatch == "ledger":
        saved.attempts = []
    else:
        saved.version = None
    checkpoint = AsyncMock()
    with (
        patch("app.services.knowledge_answer.grounded_answer", AsyncMock()) as generate,
        pytest.raises(ValueError),
    ):
        await evaluate_research.run_live(dataset, resume=saved, on_checkpoint=checkpoint)
    generate.assert_not_awaited()
    checkpoint.assert_not_awaited()


def test_attempt_accounting_includes_all_failures_and_final_result():
    dataset, saved = saved_batch(status="error")
    _, success = saved_batch()
    failed = ResearchTrial.model_validate(
        {
            **saved.trials[0].model_dump(),
            "usage": {"input_tokens": 5, "output_tokens": 1},
            "cost_usd": 0.03,
        }
    )
    completed = ResearchTrial.model_validate(
        {
            **success.trials[0].model_dump(),
            "latency_ms": 30,
            "usage": {"input_tokens": 8, "output_tokens": 2},
            "cost_usd": 0.04,
        }
    )
    report, _ = evaluate(dataset, [completed], [], attempts=[failed, completed])
    totals = report["attempt_summary"]["standard"]["development"]
    assert totals["total_latency_ms"] == 37
    assert totals["total_cost_usd"] == pytest.approx(0.07)
    assert totals["total_input_tokens"] == 13 and totals["total_output_tokens"] == 3
    assert report["rows"][0]["prior_execution_failures"] == 1
    assert report["summary"]["standard"]["development"]["confirmed_success"] == 0


@pytest.mark.parametrize(
    "problem", ["retry_completed", "changed_config", "missing_attempt", "orphan_attempt"]
)
def test_inconsistent_attempt_history_cannot_be_scored(problem):
    dataset, saved = saved_batch(status="error")
    _, success = saved_batch()
    failed, completed = saved.trials[0], success.trials[0]
    attempts, trials = [failed, completed], [completed]
    if problem == "retry_completed":
        attempts = [completed, completed]
    elif problem == "changed_config":
        failed.configuration_sha256 = "c" * 64
    elif problem == "missing_attempt":
        attempts = [failed]
    else:
        trials = []
    with pytest.raises(ValueError):
        validate_attempts(dataset, trials, attempts)


@pytest.mark.anyio
async def test_dataset_and_checkpoint_callback_mutations_do_not_change_execution():
    dataset, sample = fixture()
    expected = dataset.model_dump()
    snapshots = []

    async def capture(snapshot):
        snapshots.append(snapshot.model_copy(deep=True))
        snapshot.attempts.clear()
        dataset.cases[0].sources[0].content = "外部修改"

    async def generate(question, sources, *args, **kwargs):
        assert sources[0]["content"] == expected["cases"][0]["sources"][0]["content"]
        return standard_result(sample.answer)

    with patch("app.services.knowledge_answer.grounded_answer", side_effect=generate):
        await evaluate_research.run_live(dataset, on_checkpoint=capture)
    assert snapshots[-1].dataset_sha256 == digest(expected)
    assert len(snapshots[-1].attempts) == 1


def test_snapshot_destination_is_claimed_atomically_and_stays_private(tmp_path):
    target = tmp_path / "batch.json"

    def claim(value):
        try:
            evaluate_research.write_private(target, {"writer": value}, overwrite=False)
            return "saved"
        except FileExistsError:
            return "exists"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(claim, [1, 2]))
    assert sorted(outcomes) == ["exists", "saved"]
    assert json.loads(target.read_text())["writer"] in {1, 2}
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_paired_latency_retains_the_cost_of_failed_attempts():
    from tests.test_collaboration_benchmark import paired_trials

    dataset, standard, collaboration = paired_trials()
    standard.latency_ms, collaboration.latency_ms = 10, 20
    failed = ResearchTrial.model_validate(
        {
            **collaboration.model_dump(),
            "status": "error",
            "answer": None,
            "collaboration": None,
            "latency_ms": 30,
        }
    )
    report, _ = evaluate(
        dataset, [standard, collaboration], [], attempts=[standard, failed, collaboration]
    )
    paired = report["paired_comparison"]["development"]
    assert paired["median_collaboration_minus_standard_ms"] == 10
    assert paired["median_total_attempt_collaboration_minus_standard_ms"] == 40
    assert paired["retried_pairs"] == 1


@pytest.mark.anyio
async def test_history_capacity_is_checked_before_paying_for_an_unsavable_result(monkeypatch):
    dataset, saved = saved_batch(status="timeout")
    monkeypatch.setattr(evaluate_research, "MAX_RESEARCH_ATTEMPTS", 1)
    with (
        patch("app.services.knowledge_answer.grounded_answer", AsyncMock()) as generate,
        pytest.raises(ValueError, match="capacity"),
    ):
        await evaluate_research.run_live(dataset, resume=saved, retry_failed=True)
    generate.assert_not_awaited()


def test_pipeline_identity_changes_when_model_endpoint_changes():
    from app.core.config import settings

    before = pipeline_fingerprint()
    with patch.object(settings, "OPENAI_BASE_URL", "http://127.0.0.1:9/different"):
        assert pipeline_fingerprint() != before


@pytest.mark.anyio
async def test_cli_resume_infers_saved_routes_preserves_input_and_saves_new_ledger(
    tmp_path, monkeypatch
):
    dataset, saved = saved_batch(routes=("standard", "knowledge_collaboration"))
    cases, source, destination = [
        tmp_path / f"{name}.json" for name in ("cases", "source", "continued")
    ]
    cases.write_text(dataset.model_dump_json())
    source.write_text(saved.model_dump_json())
    before = source.read_bytes()
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_research.py",
            "--live",
            "--dataset",
            str(cases),
            "--resume-runs",
            str(source),
            "--save-runs",
            str(destination),
            "--output",
            str(tmp_path / "report.json"),
            "--packet",
            str(tmp_path / "packet.json"),
        ],
    )
    with (
        patch("app.services.knowledge_answer.grounded_answer", AsyncMock()) as standard,
        patch(
            "app.services.research_benchmark.run_source_collaboration",
            AsyncMock(return_value=collaboration_result(saved.trials[0].answer)),
        ) as collaboration,
    ):
        await evaluate_research.main()
    standard.assert_not_awaited()
    collaboration.assert_awaited_once()
    result = ResearchSnapshot.model_validate_json(destination.read_text())
    assert len(result.trials) == len(result.attempts) == 2
    assert source.read_bytes() == before


@pytest.mark.anyio
async def test_existing_snapshot_destination_is_not_overwritten_or_billed(tmp_path, monkeypatch):
    path = tmp_path / "already.json"
    path.write_text("keep")
    monkeypatch.setattr("sys.argv", ["evaluate_research.py", "--live", "--save-runs", str(path)])
    live = AsyncMock()
    monkeypatch.setattr(evaluate_research, "run_live", live)
    with pytest.raises(SystemExit):
        await evaluate_research.main()
    assert path.read_text() == "keep"
    live.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "args",
    [
        ["--retry-failed"],
        ["--resume-runs", "missing.json"],
        ["--live", "--resume-runs", "missing.json"],
    ],
)
async def test_resume_cli_flags_fail_before_any_execution(args, monkeypatch):
    monkeypatch.setattr("sys.argv", ["evaluate_research.py", *args])
    live = AsyncMock()
    monkeypatch.setattr(evaluate_research, "run_live", live)
    with pytest.raises(SystemExit):
        await evaluate_research.main()
    live.assert_not_awaited()
