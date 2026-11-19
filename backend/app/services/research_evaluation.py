"""Replay production evidence checks and aggregate explicitly reviewed research trials."""

import statistics

from app.schemas.research_evaluation import ResearchDataset, ResearchTrial, TrialReview
from app.services.knowledge_answer import GroundedAnswer, validate_answer
from app.services.research_evaluation_runs import attempt_totals, validate_attempts
from app.services.research_evaluation_runs import digest as digest


def build_record(case, trial):
    available = {s.id: s for s in case.sources}
    if trial.case_id != case.id or any(sid not in available for sid in trial.source_ids):
        raise ValueError("Trial does not match the evaluation case/source scope")
    sources = [available[sid].model_dump() for sid in trial.source_ids]
    output, cited = validate_answer(trial.answer or GroundedAnswer(sufficient=False), sources)
    approved = trial.collaboration is None or trial.collaboration.approved
    published = bool(cited) and trial.status == "completed" and approved
    if not approved:
        output = validate_answer(GroundedAnswer(sufficient=False), sources)[0]
    status = trial.status
    if status == "completed":
        status = "answered" if published else "abstained"
    trial_data = trial.model_dump()
    # Preserve fingerprints of older standard snapshots without these additive fields.
    for field in ("collaboration", "configuration_sha256"):
        if trial_data[field] is None:
            trial_data.pop(field)
    fingerprint = digest({"case": case.model_dump(), "trial": trial_data})
    claims = (
        [
            {
                "id": f"c{i}",
                "text": claim.text,
                "evidence": [e.model_dump() for e in claim.evidence],
            }
            for i, claim in enumerate(trial.answer.claims, 1)
        ]
        if published
        else []
    )
    return {
        "case_id": case.id,
        "route": trial.route,
        "split": case.split,
        "fingerprint": fingerprint,
        "status": status,
        "question": case.question,
        "requirements": [r.model_dump() for r in case.requirements],
        "sources": sources,
        "output": output if trial.status == "completed" else None,
        "claims": claims,
        "rejected_claims": len(trial.answer.claims) if trial.answer and not published else 0,
        "checks": {
            "production_quote_and_number_checks": "passed" if published else "no_published_claims",
            "semantic_support": "requires_review",
            "collaboration_review": ("approved" if approved else "rejected")
            if trial.collaboration
            else "not_applicable",
        },
        "model": trial.model,
        "latency_ms": trial.latency_ms,
        "usage": trial.usage.model_dump() if trial.usage else None,
        "cost_usd": trial.cost_usd,
        "error_type": trial.error_type,
        "collaboration": trial.collaboration.model_dump() if trial.collaboration else None,
        "configuration_sha256": trial.configuration_sha256,
    }


def review_template(record):
    return TrialReview(
        case_id=record["case_id"],
        route=record["route"],
        fingerprint=record["fingerprint"],
        claims=[{"claim_id": c["id"]} for c in record["claims"]],
        requirements=[{"requirement_id": r["id"]} for r in record["requirements"]],
    ).model_dump()


def grade_record(record, review):
    claim_ids = {c["id"] for c in record["claims"]}
    requirement_ids = {r["id"] for r in record["requirements"]}
    claims, requirements = {}, {}
    if review:
        if review.fingerprint != record["fingerprint"]:
            raise ValueError("Review fingerprint is stale")
        if (review.case_id, review.route) != (record["case_id"], record["route"]):
            raise ValueError("Review belongs to another trial")
        for item in review.claims:
            if item.claim_id not in claim_ids or item.claim_id in claims:
                raise ValueError("Unknown or duplicate reviewed claim")
            claims[item.claim_id] = item.support
        for item in review.requirements:
            if item.requirement_id not in requirement_ids or item.requirement_id in requirements:
                raise ValueError("Unknown or duplicate reviewed requirement")
            if (
                len(set(item.claim_ids)) != len(item.claim_ids)
                or not set(item.claim_ids) <= claim_ids
            ):
                raise ValueError("Unknown or duplicate requirement claim link")
            requirements[item.requirement_id] = item.status
            if (
                record["status"] == "answered"
                and item.status == "satisfied"
                and (
                    not item.claim_ids
                    or any(claims.get(cid) != "supported" for cid in item.claim_ids)
                )
            ):
                raise ValueError("Satisfied requirements must link to reviewed supported claims")
        judgments = [*claims.values(), *requirements.values(), review.abstention]
        if any(j is not None for j in judgments) and not (review.reviewer or "").strip():
            raise ValueError("Semantic judgments require a reviewer label")
        if review.abstention is not None and record["status"] != "abstained":
            raise ValueError("Only an abstained trial can have an abstention judgment")
        if record["status"] in {"error", "timeout"} and any(j is not None for j in judgments):
            raise ValueError("Execution failures cannot be graded as answered or abstained")
    supported = sum(v == "supported" for v in claims.values())
    satisfied = sum(v == "satisfied" for v in requirements.values())
    confirmed = (
        record["status"] in {"answered", "abstained"}
        and satisfied == len(requirement_ids)
        and (
            supported == len(claim_ids)
            if record["status"] == "answered"
            else bool(review and review.abstention == "correct")
        )
    )
    complete = record["status"] in {"error", "timeout"} or (
        sum(v is not None for v in claims.values()) == len(claim_ids)
        and sum(v is not None for v in requirements.values()) == len(requirement_ids)
        and (record["status"] != "abstained" or bool(review and review.abstention is not None))
    )
    return {
        "case_id": record["case_id"],
        "route": record["route"],
        "split": record["split"],
        "fingerprint": record["fingerprint"],
        "status": record["status"],
        "claims": len(claim_ids),
        "claims_reviewed": sum(v is not None for v in claims.values()),
        "claims_supported": supported,
        "requirements": len(requirement_ids),
        "requirements_reviewed": sum(v is not None for v in requirements.values()),
        "requirements_satisfied": satisfied,
        "correct_abstention": bool(review and review.abstention == "correct"),
        "abstention_reviewed": bool(review and review.abstention is not None),
        "confirmed_success": confirmed,
        "reviewer": review.reviewer if review else None,
        "review_sha256": digest(review.model_dump()) if review else None,
        "abstention_assessment": review.abstention if review else None,
        "assessment_complete": complete,
        "assessment_resolved": complete
        and "uncertain" not in [*claims.values(), *requirements.values()]
        and not (review and review.abstention == "uncertain"),
        "claim_assessments": [item.model_dump() for item in review.claims] if review else [],
        "requirement_assessments": [item.model_dump() for item in review.requirements]
        if review
        else [],
        **{key: record[key] for key in ("latency_ms", "usage", "cost_usd", "model")},
    }


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def summarize(rows, expected_cases):
    counts = {
        key: sum(r[key] for r in rows)
        for key in (
            "claims",
            "claims_reviewed",
            "claims_supported",
            "requirements",
            "requirements_reviewed",
            "requirements_satisfied",
            "abstention_reviewed",
            "correct_abstention",
            "confirmed_success",
        )
    }
    latencies = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
    usages = [r["usage"] for r in rows if r["usage"] is not None]
    costs = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
    return {
        "expected_cases": expected_cases,
        "recorded_cases": len(rows),
        "missing_cases": expected_cases - len(rows),
        "answered": sum(r["status"] == "answered" for r in rows),
        "abstained": sum(r["status"] == "abstained" for r in rows),
        "errors": sum(r["status"] in {"error", "timeout"} for r in rows),
        **counts,
        "citation_support_accuracy_reviewed": ratio(
            counts["claims_supported"], counts["claims_reviewed"]
        ),
        "claim_review_coverage": ratio(counts["claims_reviewed"], counts["claims"]),
        "requirement_satisfaction_reviewed": ratio(
            counts["requirements_satisfied"], counts["requirements_reviewed"]
        ),
        "requirement_review_coverage_recorded": ratio(
            counts["requirements_reviewed"], counts["requirements"]
        ),
        "confirmed_success_rate": ratio(counts["confirmed_success"], expected_cases),
        "median_ms_recorded": statistics.median(latencies) if latencies else None,
        "latency_measured_cases": len(latencies),
        "usage_measured_cases": len(usages),
        "measured_input_tokens": sum(u["input_tokens"] for u in usages) if usages else None,
        "measured_output_tokens": sum(u["output_tokens"] for u in usages) if usages else None,
        "cost_measured_cases": len(costs),
        "measured_cost_usd": sum(costs) if costs else None,
    }


def paired_comparison(records, rows, expected_cases):
    grouped, grades = {}, {(r["case_id"], r["route"]): r for r in rows}
    for record in records:
        grouped.setdefault(record["case_id"], {})[record["route"]] = record
    pairs = [pair for pair in grouped.values() if len(pair) == 2]
    comparable, input_mismatch, model_mismatch, config_mismatch = [], 0, 0, 0
    for pair in pairs:
        standard, collaboration = pair["standard"], pair["knowledge_collaboration"]
        if standard["sources"] != collaboration["sources"]:
            input_mismatch += 1
        elif standard["model"] != collaboration["model"]:
            model_mismatch += 1
        elif (
            not standard["configuration_sha256"]
            or standard["configuration_sha256"] != collaboration["configuration_sha256"]
        ):
            config_mismatch += 1
        else:
            comparable.append((standard, collaboration))
    reviewed, outcomes, deltas = (
        0,
        {
            "both_successful": 0,
            "standard_only_successful": 0,
            "collaboration_only_successful": 0,
            "neither_successful": 0,
        },
        [],
    )
    total_deltas, retried_pairs = [], 0
    for standard, collaboration in comparable:
        left, right = [grades[(r["case_id"], r["route"])] for r in (standard, collaboration)]
        retried_pairs += any(r["attempt_count"] > 1 for r in (left, right))
        if all(r["latency_ms"] is not None for r in (left, right)):
            deltas.append(right["latency_ms"] - left["latency_ms"])
        if all(r["total_attempt_latency_ms"] is not None for r in (left, right)):
            total_deltas.append(
                right["total_attempt_latency_ms"] - left["total_attempt_latency_ms"]
            )
        if not (left["assessment_resolved"] and right["assessment_resolved"]):
            continue
        reviewed += 1
        success = left["confirmed_success"], right["confirmed_success"]
        label = {
            (True, True): "both_successful",
            (True, False): "standard_only_successful",
            (False, True): "collaboration_only_successful",
            (False, False): "neither_successful",
        }[success]
        outcomes[label] += 1
    return {
        "expected_pairs": expected_cases,
        "recorded_pairs": len(pairs),
        "missing_pairs": expected_cases - len(pairs),
        "comparable_pairs": len(comparable),
        "source_mismatch_pairs": input_mismatch,
        "model_mismatch_pairs": model_mismatch,
        "unknown_or_mismatched_configuration_pairs": config_mismatch,
        "reviewed_pairs": reviewed,
        "pending_review_pairs": len(comparable) - reviewed,
        **outcomes,
        "latency_measured_pairs": len(deltas),
        "median_collaboration_minus_standard_ms": statistics.median(deltas) if deltas else None,
        "total_attempt_latency_measured_pairs": len(total_deltas),
        "retried_pairs": retried_pairs,
        "median_total_attempt_collaboration_minus_standard_ms": statistics.median(total_deltas)
        if total_deltas
        else None,
    }


def evaluate(
    dataset: ResearchDataset,
    trials: list[ResearchTrial],
    reviews: list[TrialReview],
    *,
    attempts=None,
):
    histories = validate_attempts(dataset, trials, attempts)
    cases = {case.id: case for case in dataset.cases}
    records, keys = [], set()
    for trial in trials:
        key = (trial.case_id, trial.route)
        if key in keys or trial.case_id not in cases:
            raise ValueError("Unknown or duplicate trial")
        keys.add(key)
        records.append(build_record(cases[trial.case_id], trial))
    by_review = {}
    for review in reviews:
        key = (review.case_id, review.route)
        if key in by_review or key not in keys:
            raise ValueError("Unknown or duplicate review")
        by_review[key] = review
    rows = [grade_record(r, by_review.get((r["case_id"], r["route"]))) for r in records]
    for row in rows:
        history = histories[(row["case_id"], row["route"])]
        row["attempt_count"] = len(history)
        row["prior_execution_failures"] = len(history) - 1
        row["attempts_sha256"] = digest([t.model_dump() for t in history])
        row["total_attempt_latency_ms"] = attempt_totals(history)["total_latency_ms"]
    summaries = {}
    for route in ("standard", "knowledge_collaboration"):
        summaries[route] = {}
        for split in ("development", "holdout"):
            subset = [r for r in rows if r["route"] == route and r["split"] == split]
            summaries[route][split] = summarize(
                subset, sum(c.split == split for c in dataset.cases)
            )
    return {
        "version": "research-evaluation-v1",
        "dataset_sha256": digest(dataset.model_dump()),
        "origin": dataset.origin,
        "summary": summaries,
        "attempt_summary": {
            route: {
                split: attempt_totals(
                    [
                        attempt
                        for (case_id, trial_route), history in histories.items()
                        if trial_route == route and cases[case_id].split == split
                        for attempt in history
                    ]
                )
                for split in ("development", "holdout")
            }
            for route in ("standard", "knowledge_collaboration")
        },
        "paired_comparison": {
            split: paired_comparison(
                [r for r in records if r["split"] == split],
                [r for r in rows if r["split"] == split],
                sum(c.split == split for c in dataset.cases),
            )
            for split in ("development", "holdout")
        },
        "rows": rows,
    }, {
        "version": "research-review-packet-v1",
        "records": records,
        "reviews": [review_template(r) for r in records],
    }
