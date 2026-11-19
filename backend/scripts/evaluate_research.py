"""Source-provided research benchmark: offline validation/replay or explicit --live.

Run from /tmp with PYTHONPATH set to backend. Live uses the configured generation
model, never an embedding model or database. It measures source-grounded generation,
not end-to-end retrieval, sandbox execution or production success.
"""

import argparse
import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from app.schemas.research_evaluation import (
    MAX_RESEARCH_ATTEMPTS,
    ResearchDataset,
    ResearchSnapshot,
    ResearchTrial,
    TrialReview,
)
from app.services.research_evaluation import digest, evaluate
from app.services.research_evaluation_runs import pipeline_fingerprint, validate_resume


def write_private(path, value, *, overwrite=True):
    """Atomic, owner-only artifacts; review packets may contain private source text."""
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".research-eval-", delete=False
        ) as stream:
            temporary = stream.name
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            # Atomic no-clobber creation, including concurrent writers to this path.
            os.link(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


async def run_live(
    dataset: ResearchDataset,
    *,
    routes=("standard",),
    on_trial=None,
    on_checkpoint=None,
    resume: ResearchSnapshot | None = None,
    retry_failed=False,
) -> list[ResearchTrial]:
    from app.services.knowledge_answer import GroundedAnswer, grounded_answer
    from app.services.model_config import resolve_generation_config
    from app.services.research_benchmark import run_source_collaboration

    if (
        not routes
        or len(set(routes)) != len(routes)
        or any(route not in {"standard", "knowledge_collaboration"} for route in routes)
    ):
        raise ValueError("Invalid benchmark routes")
    config = resolve_generation_config({})
    dataset = ResearchDataset.model_validate(dataset.model_dump())
    configuration_sha256, pipeline_sha256 = digest(config.model_dump()), pipeline_fingerprint()
    if retry_failed and resume is None:
        raise ValueError("Retry requires a saved batch")
    if resume is not None:
        resume = ResearchSnapshot.model_validate(resume.model_dump())
        validate_resume(
            dataset,
            resume,
            routes=routes,
            model=config.model,
            configuration_sha256=configuration_sha256,
            pipeline_sha256=pipeline_sha256,
        )
    checkpoint = resume or ResearchSnapshot.model_validate(
        {
            "version": "research-run-snapshot-v1",
            "dataset_sha256": digest(dataset.model_dump()),
            "model": config.model,
            "configuration_sha256": configuration_sha256,
            "pipeline_sha256": pipeline_sha256,
            "routes": list(routes),
            "trials": [],
            "attempts": [],
        }
    )
    effective = {(t.case_id, t.route): t for t in checkpoint.trials}
    attempts = list(checkpoint.attempts or [])
    pending = sum(
        (case.id, route) not in effective
        or (retry_failed and effective[(case.id, route)].status in {"error", "timeout"})
        for case in dataset.cases
        for route in routes
    )
    if len(attempts) + pending > MAX_RESEARCH_ATTEMPTS:
        raise ValueError("Attempt ledger capacity exceeded; start a new evaluation batch")

    async def publish_checkpoint():
        checkpoint.trials, checkpoint.attempts = list(effective.values()), list(attempts)
        if on_checkpoint:
            await on_checkpoint(checkpoint.model_copy(deep=True))

    # Validate and claim the destination before any paid request; also save an empty manifest.
    await publish_checkpoint()
    for position, case in enumerate(dataset.cases):
        # Alternate order to reduce systematic warm-up/order bias; contexts stay separate.
        for route in routes if position % 2 == 0 else tuple(reversed(routes)):
            previous = effective.get((case.id, route))
            if previous is not None and (previous.status == "completed" or not retry_failed):
                print(f"{case.id}/{route}: retained {previous.status}", flush=True)
                continue
            started = time.monotonic()
            common: dict[str, Any] = {
                "case_id": case.id,
                "route": route,
                "model": config.model,
                "configuration_sha256": configuration_sha256,
                "source_ids": [s.id for s in case.sources],
            }
            try:
                if route == "standard":
                    _, _, meta = await grounded_answer(
                        case.question,
                        [s.model_dump() for s in case.sources],
                        None,
                        configuration=config,
                        include_evaluation=True,
                    )
                    detail = meta["evaluation"]
                else:
                    detail = await run_source_collaboration(case, config)
                trial = ResearchTrial(
                    **common,
                    status="completed",
                    answer=GroundedAnswer.model_validate(detail["answer"]),
                    usage=detail["usage"],
                    collaboration=detail.get("collaboration"),
                    latency_ms=round((time.monotonic() - started) * 1000),
                )
            except Exception as exc:
                trial = ResearchTrial(
                    **common,
                    status="timeout" if isinstance(exc, TimeoutError) else "error",
                    error_type=type(exc).__name__,
                    latency_ms=round((time.monotonic() - started) * 1000),
                )
            effective[(case.id, route)] = trial
            attempts.append(trial)
            await publish_checkpoint()
            if on_trial:
                await on_trial([t.model_copy(deep=True) for t in effective.values()])
            print(f"{case.id}/{route}: {trial.status}", flush=True)
    return list(effective.values())


async def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "evals/research_tasks_v1.json",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="Paid model calls for selected routes")
    parser.add_argument(
        "--route", choices=["standard", "knowledge_collaboration", "both"], default=None
    )
    mode.add_argument("--runs", type=Path, help="Replay captured trials from either route")
    mode.add_argument(
        "--knowledge-report", type=Path, help="Replay evaluate_knowledge --answers output"
    )
    parser.add_argument("--reviews", type=Path, help="Manually completed review packet")
    parser.add_argument("--output", type=Path, default=Path("/tmp/research-evaluation-report.json"))
    parser.add_argument("--packet", type=Path, default=Path("/tmp/research-review-packet.json"))
    parser.add_argument(
        "--save-runs", type=Path, help="Save live snapshots for later offline review"
    )
    parser.add_argument(
        "--resume-runs", type=Path, help="Continue a versioned batch into a new --save-runs file"
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry saved errors/timeouts once; keep every attempt",
    )
    args = parser.parse_args()
    input_paths = {
        p.resolve()
        for p in (args.dataset, args.runs, args.resume_runs, args.knowledge_report, args.reviews)
        if p
    }
    output_paths = [p.resolve() for p in (args.output, args.packet, args.save_runs) if p]
    if len(set(output_paths)) != len(output_paths) or input_paths.intersection(output_paths):
        parser.error("Output files must differ from each other and from all inputs")
    if args.reviews and not (args.runs or args.knowledge_report):
        parser.error("Reviews require a captured --runs or --knowledge-report snapshot")
    if args.save_runs and not args.live:
        parser.error("--save-runs requires --live")
    if args.route is not None and not args.live:
        parser.error("--route requires --live; replay uses the route saved in each snapshot")
    if args.resume_runs and (not args.live or not args.save_runs):
        parser.error("--resume-runs requires --live and a different --save-runs destination")
    if args.retry_failed and not args.resume_runs:
        parser.error("--retry-failed requires --resume-runs")
    if args.save_runs and args.save_runs.exists():
        parser.error("--save-runs must be new; use --resume-runs to continue an existing batch")
    captured = json.loads(args.knowledge_report.read_text()) if args.knowledge_report else None
    dataset = (
        ResearchDataset.model_validate(captured["research_dataset"])
        if captured is not None
        else ResearchDataset.model_validate_json(args.dataset.read_text())
    )
    if not args.live and not args.runs and captured is None:
        print(
            json.dumps(
                {
                    "mode": "offline",
                    "cases": len(dataset.cases),
                    "origin": dataset.origin,
                    "limitation": "Dataset validation only; no model quality measured.",
                }
            )
        )
        return
    if args.live:
        saved = (
            ResearchSnapshot.model_validate_json(args.resume_runs.read_text())
            if args.resume_runs
            else None
        )
        last_checkpoint = None
        created = False

        async def save_progress(snapshot):
            nonlocal last_checkpoint, created
            if args.save_runs:
                write_private(args.save_runs, snapshot.model_dump(), overwrite=created)
                created = True
            last_checkpoint = snapshot

        if args.route == "both":
            routes = ("standard", "knowledge_collaboration")
        elif args.route:
            routes = (args.route,)
        elif saved is not None:
            if saved.routes is None:
                parser.error(
                    "Legacy snapshots support offline replay only; resume needs an execution manifest"
                )
            routes = tuple(saved.routes)
        else:
            routes = ("standard",)
        trials = await run_live(
            dataset,
            routes=routes,
            on_checkpoint=save_progress,
            resume=saved,
            retry_failed=args.retry_failed,
        )
        attempts = last_checkpoint.attempts if last_checkpoint is not None else None
    else:
        if captured is not None:
            trial_rows = captured["research_trials"]
        else:
            snapshot = ResearchSnapshot.model_validate_json(args.runs.read_text())
            if snapshot.dataset_sha256 not in (None, digest(dataset.model_dump())):
                parser.error("Run snapshot belongs to a different dataset revision")
            trial_rows = snapshot.trials
        trials = [
            row if isinstance(row, ResearchTrial) else ResearchTrial.model_validate(row)
            for row in trial_rows
        ]
        attempts = None if captured is not None else snapshot.attempts
    reviews = (
        [TrialReview.model_validate(row) for row in json.loads(args.reviews.read_text())["reviews"]]
        if args.reviews
        else []
    )
    report, packet = evaluate(dataset, trials, reviews, attempts=attempts)
    report["mode"] = "live_sources_provided" if args.live else "snapshot_replay"
    report["limitations"] = [
        "Semantic judgments are reviewer-supplied, not independent factual proof.",
        "Source-provided generation/replay does not measure retrieval or sandbox execution.",
        "Authored cases are not a production quality estimate; missing reviews remain unconfirmed.",
    ]
    write_private(args.output, report)
    write_private(args.packet, packet)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
