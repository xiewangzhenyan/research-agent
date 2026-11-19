"""Evaluation attempt ledgers and strict batch resume boundaries; no model calls."""

import hashlib
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def pipeline_fingerprint():
    from app.core.config import settings

    root = Path(__file__).resolve().parents[2]
    files = (
        "app/agents/model.py",
        "app/agents/factory.py",
        "app/agents/policy.py",
        "app/schemas/knowledge_answer.py",
        "app/schemas/research_evaluation.py",
        "app/schemas/agent_handoff.py",
        "app/services/agent_handoff.py",
        "app/services/context_budget.py",
        "app/services/model_config.py",
        "app/services/knowledge_answer.py",
        "app/services/knowledge_collaboration.py",
        "app/services/research_benchmark.py",
        "app/services/research_evaluation_runs.py",
        "scripts/evaluate_research.py",
        "uv.lock",
    )
    return digest(
        {
            "files": {
                name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files
            },
            "model_endpoint": str(settings.OPENAI_BASE_URL),
        }
    )


def validate_attempts(dataset, trials, attempts=None):
    """Only execution failures can be retried; the effective result is the last attempt."""
    cases = {case.id: case for case in dataset.cases}
    latest, groups = {}, {}
    for trial in trials:
        key = trial.case_id, trial.route
        if key in latest or trial.case_id not in cases:
            raise ValueError("Unknown or duplicate trial")
        latest[key] = trial
    for attempt in trials if attempts is None else attempts:
        key = attempt.case_id, attempt.route
        if key not in latest:
            raise ValueError("Attempt has no corresponding effective trial")
        if not set(attempt.source_ids) <= {s.id for s in cases[attempt.case_id].sources}:
            raise ValueError("Attempt sources are outside the case scope")
        group = groups.setdefault(key, [])
        if group:
            if group[-1].status == "completed":
                raise ValueError("Completed results, including abstentions, cannot be retried")
            if any(
                getattr(group[-1], field) != getattr(attempt, field)
                for field in (
                    "source_ids",
                    "model",
                    "configuration_sha256",
                )
            ):
                raise ValueError("Retry changed source scope, model or configuration")
        group.append(attempt)
    if groups.keys() != latest.keys() or any(
        group[-1].model_dump() != latest[key].model_dump() for key, group in groups.items()
    ):
        raise ValueError("Attempt ledger does not match effective results")
    return groups


def validate_resume(dataset, snapshot, *, routes, model, configuration_sha256, pipeline_sha256):
    if snapshot.version != "research-run-snapshot-v1":
        raise ValueError(
            "Legacy snapshots support offline replay only; resume needs an execution manifest"
        )
    if snapshot.dataset_sha256 != digest(dataset.model_dump()):
        raise ValueError("Resume dataset revision changed")
    if snapshot.model != model or snapshot.configuration_sha256 != configuration_sha256:
        raise ValueError("Resume model or generation configuration changed")
    if snapshot.pipeline_sha256 != pipeline_sha256:
        raise ValueError("Resume pipeline code changed")
    if tuple(snapshot.routes) != tuple(routes):
        raise ValueError("Resume route plan changed")
    groups = validate_attempts(dataset, snapshot.trials, snapshot.attempts)
    cases = {case.id: case for case in dataset.cases}
    for (case_id, route), group in groups.items():
        for trial in group:
            if (
                route not in routes
                or trial.model != model
                or trial.configuration_sha256 != configuration_sha256
                or trial.source_ids != [s.id for s in cases[case_id].sources]
            ):
                raise ValueError("Resume trial does not match the fixed-source execution manifest")


def attempt_totals(attempts):
    latencies = [a.latency_ms for a in attempts if a.latency_ms is not None]
    usages = [a.usage for a in attempts if a.usage is not None]
    costs = [a.cost_usd for a in attempts if a.cost_usd is not None]
    counts, first, last = {}, {}, {}
    for attempt in attempts:
        key = attempt.case_id, attempt.route
        counts[key] = counts.get(key, 0) + 1
        first.setdefault(key, attempt)
        last[key] = attempt
    return {
        "recorded_attempts": len(attempts),
        "failed_attempts": sum(a.status in {"error", "timeout"} for a in attempts),
        "retried_cases": sum(n > 1 for n in counts.values()),
        "first_attempt_completed_cases": sum(a.status == "completed" for a in first.values()),
        "completed_after_retry_cases": sum(
            n > 1 and last[key].status == "completed" for key, n in counts.items()
        ),
        "latency_measured_attempts": len(latencies),
        "measured_latency_ms": sum(latencies) if latencies else None,
        "total_latency_ms": sum(latencies)
        if attempts and len(latencies) == len(attempts)
        else None,
        "usage_measured_attempts": len(usages),
        "measured_input_tokens": sum(u.input_tokens for u in usages) if usages else None,
        "measured_output_tokens": sum(u.output_tokens for u in usages) if usages else None,
        "total_input_tokens": sum(u.input_tokens for u in usages)
        if attempts and len(usages) == len(attempts)
        else None,
        "total_output_tokens": sum(u.output_tokens for u in usages)
        if attempts and len(usages) == len(attempts)
        else None,
        "cost_measured_attempts": len(costs),
        "measured_cost_usd": sum(costs) if costs else None,
        "total_cost_usd": sum(costs) if attempts and len(costs) == len(attempts) else None,
    }
