"""Jev routing smoke evaluation. Default is offline; --live makes paid API calls.

Run from /tmp with PYTHONPATH pointing at backend to avoid loading production
settings. --env-file reads only JEV_* values, never generation or DB credentials.
Reports contain case IDs and decisions, without question text or credentials.
"""

import argparse
import asyncio
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from app.clients.jev import ROUTING_POLICY, classify_route
from app.core.config import Settings, settings


def summarize(rows):
    answered = [row for row in rows if row["status"] == "classified"]
    accepted = [row for row in answered if row["recommendation"] is not None]
    latencies = sorted(row["latency_ms"] for row in rows)
    return {
        "cases": len(rows),
        "classified": len(answered),
        "raw_choice_accuracy": sum(row["choice"] == row["expected"] for row in answered)
        / len(answered)
        if answered
        else None,
        "accepted": len(accepted),
        "accepted_accuracy": sum(row["recommendation"] == row["expected"] for row in accepted)
        / len(accepted)
        if accepted
        else None,
        "fallback_cases": len(rows) - len(accepted),
        "incorrect_collaboration_upgrades": sum(
            row["recommendation"] == "knowledge_collaboration"
            and row["expected"] != "knowledge_collaboration"
            for row in answered
        ),
        "missed_collaboration_cases": sum(
            row["expected"] == "knowledge_collaboration"
            and row["recommendation"] != "knowledge_collaboration"
            for row in rows
        ),
        "median_ms": statistics.median(latencies) if latencies else None,
        "p95_ms": latencies[math.ceil(len(latencies) * 0.95) - 1] if latencies else None,
        "input_tokens": sum(row.get("usage", {}).get("input_tokens", 0) for row in rows),
    }


async def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path, default=Path("/tmp/research-routing-report.json"))
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "evals/routing_v1.json",
    )
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text())
    cases = dataset["cases"]
    if not args.live:
        print(json.dumps({"mode": "offline", "cases": len(cases), "policy": ROUTING_POLICY}))
        return
    if args.env_file:
        values: dict[str, Any] = {
            k: v for k, v in dotenv_values(args.env_file).items() if k.startswith("JEV_")
        }
        config = Settings(_env_file=None, **values)
        for key in values:
            setattr(settings, key, getattr(config, key))
    if not settings.JEV_API_KEY.get_secret_value():
        parser.error("JEV_API_KEY is required for --live")
    rows = []
    for case in cases:
        started = time.monotonic()
        row = {"id": case["id"], "expected": case["expected"], "recommendation": None}
        try:
            result = await classify_route(case["prompt"], case["prompt"])
            answer = result.answers["route"]
            row.update(
                status="classified",
                choice=answer.choice,
                confidence=answer.confidence,
                recommendation=answer.recommendation(settings.JEV_MIN_CONFIDENCE),
                model=result.model,
                usage=result.usage,
            )
        except Exception as exc:
            row.update(status="unavailable", error_type=type(exc).__name__)
        row["latency_ms"] = round((time.monotonic() - started) * 1000)
        rows.append(row)
        print(f"{case['id']}: {row['status']}", flush=True)
    report = {
        "policy": ROUTING_POLICY,
        "dataset": dataset["version"],
        "threshold": settings.JEV_MIN_CONFIDENCE,
        "limitation": "Authored smoke cases; not a production accuracy estimate.",
        "summary": summarize(rows),
        "rows": rows,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
