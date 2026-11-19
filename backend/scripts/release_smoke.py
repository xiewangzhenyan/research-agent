"""Explicit live acceptance using only synthetic markers; never writes business data.

Run in the prepared backend container so the gateway/network match deployment.
Default is offline. --live --model makes at most three bounded model requests;
--live --sandbox runs two small isolated jobs and cancels only its own run ID.
Credentials come from the runtime environment, never printed or read from files.
"""

import argparse
import asyncio
import base64
import hashlib
import json
from uuid import uuid4


async def model_smoke():
    from typing import Literal

    from pydantic import BaseModel

    from app.agents.factory import AgentDefinition, create_agent
    from app.agents.policy import ExecutionLimits
    from app.agents.runtime import run_tools
    from app.services.model_config import resolve_generation_config

    config = resolve_generation_config({"max_output_tokens": 512, "thinking_effort": "off"})
    definition = AgentDefinition(
        name="release-probe",
        system_prompt="For this synthetic release check, first call echo_release_probe with value RELEASE_OK, then reply exactly RELEASE_OK. No other content.",
        limits=ExecutionLimits(requests=2, tools=1, tokens=6000, timeout=35),
    )
    registry = create_agent(definition, config).registry()
    effects = []

    @registry.register_plain
    def echo_release_probe(value: Literal["RELEASE_OK"]) -> dict:
        """Echo the fixed synthetic release marker, with no side effects."""
        effects.append(value)
        return {"marker": value}

    async with asyncio.timeout(90):
        result = await run_tools(
            registry, "Run the release probe now", request_limit=2, token_limit=6000, tool_limit=1
        )
    if effects != ["RELEASE_OK"] or result["output"].strip() != "RELEASE_OK":
        raise ValueError("Native tool stream acceptance failed")

    class ProbeResult(BaseModel):
        marker: Literal["RELEASE_OK"]

    role = create_agent(
        AgentDefinition(
            name="release-structured-probe",
            system_prompt="Return the marker RELEASE_OK.",
            output_schema=ProbeResult,
            limits=ExecutionLimits(requests=1, tokens=3000, timeout=35),
            output_tokens=512,
            retries=0,
        ),
        config,
    )
    structured = await role.structured("Return the fixed release marker.")
    if structured.output.marker != "RELEASE_OK":
        raise ValueError("Structured acceptance failed")
    return {
        "status": "passed",
        "model": config.model,
        "checks": ["responses_tool_stream", "typed_tool_dispatch", "structured_schema"],
    }


async def sandbox_smoke():
    from app.services import sandbox_client
    from app.services.artifact_validation import inspect_artifact

    health = await sandbox_client.health()
    if health.get("status") != "ready" or not health.get("file_execution"):
        return {"status": health.get("status", "unavailable"), "checks": []}
    run_id = uuid4()
    payload = b"value\n1\n2\n"
    inputs = [
        {
            "name": "probe.csv",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "content_base64": base64.b64encode(payload).decode(),
        }
    ]
    try:
        first = await sandbox_client.run_python(
            run_id,
            """from pathlib import Path
import csv
path = Path('/inputs/probe.csv')
try:
    path.write_text('changed')
except OSError:
    pass
else:
    raise RuntimeError('Input was writable')
total = sum(int(row['value']) for row in csv.DictReader(path.open()))
assert total == 3
Path('/work/outputs/result.csv').write_text('total\\n3\\n')
print('RELEASE_SANDBOX_OK')
""",
            protocol=2,
            inputs=inputs,
        )
        if first["state"] != "completed" or "RELEASE_SANDBOX_OK" not in first.get("stdout", ""):
            raise ValueError("Sandbox computation failed")
        files = first.get("artifact_files", [])
        if len(files) != 1 or files[0]["content"] != b"total\n3\n":
            raise ValueError("Sandbox artifact failed")
        inspect_artifact(files[0])
        reused = [
            {
                "name": "previous.csv",
                "sha256": files[0]["sha256"],
                "content_base64": base64.b64encode(files[0]["content"]).decode(),
            }
        ]
        second = await sandbox_client.run_python(
            run_id,
            "from pathlib import Path; assert Path('/inputs/previous.csv').read_text() == 'total\\n3\\n'; print('RELEASE_REUSE_OK')",
            protocol=2,
            inputs=reused,
        )
        if second["state"] != "completed" or "RELEASE_REUSE_OK" not in second.get("stdout", ""):
            raise ValueError("Sandbox reuse failed")
        return {
            "status": "passed",
            "checks": [
                "sandbox_file_protocol",
                "read_only_inputs",
                "artifact_bytes",
                "artifact_reuse",
            ],
        }
    finally:
        await sandbox_client.cancel_run(run_id)


async def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model", action="store_true")
    parser.add_argument("--sandbox", action="store_true")
    args = parser.parse_args()
    if not args.live:
        print(
            json.dumps(
                {"mode": "offline", "calls": 0, "note": "Use --live with --model and/or --sandbox"}
            )
        )
        return 0
    if not (args.model or args.sandbox):
        parser.error("Select --model and/or --sandbox")
    report = {"mode": "live", "business_data_written": False, "checks": {}}
    for selected, name, call in (
        (args.model, "model", model_smoke),
        (args.sandbox, "sandbox", sandbox_smoke),
    ):
        if not selected:
            continue
        try:
            report["checks"][name] = await call()
        except Exception as exc:
            report["checks"][name] = {
                "status": "failed",
                "error_type": type(exc).__name__,
                "http_status": getattr(exc, "status_code", None),
            }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if all(check["status"] == "passed" for check in report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
