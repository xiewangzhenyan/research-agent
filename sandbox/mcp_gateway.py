"""Ephemeral Stdio jobs share the code runner's resource budget and tombstones."""

import asyncio
import json
import re
import time
from typing import Literal
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator


class MCPRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: UUID
    command: str = Field(min_length=1, max_length=200)
    args: list[str] = Field(default_factory=list, max_length=30)
    env: dict[str, str] = Field(default_factory=dict, repr=False)
    operation: Literal["discover", "call"] = "discover"
    name: str | None = Field(default=None, max_length=128)
    arguments: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def bounded(self):
        if self.command not in ("python", "python3", "/usr/local/bin/python"):
            raise ValueError("Only installed Python runtime is supported")
        if any(len(a) > 1000 or "\x00" in a for a in self.args):
            raise ValueError("Invalid arguments")
        if len(json.dumps(self.env)) > 20000 or len(json.dumps(self.arguments)) > 6000:
            raise ValueError("Payload limit exceeded")
        for key, value in self.env.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,99}", key) or any(
                c in value for c in "\x00\r\n"
            ):
                raise ValueError("Invalid environment")
        if self.operation == "call" and not self.name:
            raise ValueError("Tool name required")
        return self


class MCPGateway:
    def __init__(self, runner, image, spec_factory):
        self.runner, self.image, self.spec_factory = runner, image, spec_factory
        self.active = {}
        self.probe_until = 0.0
        self.probe_lock = asyncio.Lock()

    async def execute(self, body):
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", self.image):
            raise HTTPException(503, "MCP runtime unavailable")
        # Shared with 512 MiB file jobs: never start a second workload on a 1 GiB node.
        try:
            await asyncio.wait_for(self.runner.slots.acquire(), 2)
        except TimeoutError:
            raise HTTPException(429, "Sandbox busy; retry later") from None
        job_id = uuid4()
        name = "agent-mcp-" + str(job_id)
        try:
            async with asyncio.timeout(28):
                await self.runner.engine.ready(self.image)
                spec = self.spec_factory(self.image, "", body.run_id, job_id)
                spec["Entrypoint"] = ["python", "-I", "-B", "/opt/agent-mcp-runner.py"]
                spec["Cmd"] = []
                spec["Env"].append("AGENT_MCP_REQUEST=" + body.model_dump_json())
                spec["Labels"]["agent.phase"] = "mcp"
                # No retry or durable secret-bearing payload on the execution node.
                async with self.runner.lifecycle:
                    if self.runner.cancelled(body.run_id):
                        raise HTTPException(409, "Run cancelled")
                    self.active[name] = str(body.run_id)
                    await self.runner.engine.ensure(name, spec)
                while True:
                    info = await self.runner.engine.inspect(name)
                    if not info:
                        raise HTTPException(409, "Execution cancelled or removed")
                    if not info["State"].get("Running"):
                        break
                    await asyncio.sleep(0.1)
                logs = await self.runner.engine.logs(name)
                if info["State"].get("ExitCode") != 0 or logs["truncated"]:
                    raise ValueError("Execution failed or output exceeded limit")
                value = json.loads(logs["stdout"])
                if value.get("ok") is not True or not isinstance(value.get("result"), dict):
                    raise ValueError("MCP exchange failed")
                return value["result"]
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                503, "MCP failed: check installed command, protocol and size limits"
            ) from None
        finally:
            try:
                cleanup = asyncio.create_task(self.runner.engine.remove(name))
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    await cleanup
                    raise
            finally:
                self.active.pop(name, None)
                self.runner.slots.release()

    async def cancel(self, run_id):
        async with self.runner.lifecycle:
            for name, owner in list(self.active.items()):
                if owner == str(run_id):
                    # Stop is idempotent with the exchange's finally cleanup.
                    # Concurrent Docker DELETEs can return "removal in progress".
                    await self.runner.engine.stop(name)

    async def health(self):
        async with self.probe_lock:
            if self.probe_until <= time.monotonic():
                result = await self.execute(
                    MCPRequest(
                        run_id=uuid4(),
                        command="python",
                        args=[
                            "-c",
                            "from mcp.server.fastmcp import FastMCP; m=FastMCP('probe'); m.run()",
                        ],
                    )
                )
                if result != {"tools": [], "resources": [], "prompts": []}:
                    raise HTTPException(503, "MCP self-test failed")
                self.probe_until = time.monotonic() + 60
        return {
            "status": "ready",
            "protocol": 1,
            "runtime": "runsc",
            "image": self.image,
            "network": "none",
            "commands": ["python", "python3"],
            "output_bytes": 30000,
        }
