"""Independent control plane. Deploy on an execution-only node, one process.

Only this service has Docker access. Code containers receive neither that socket
nor service credentials, host paths, network access or a writable root filesystem.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager, suppress
from typing import Literal
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, model_validator

try:
    from .mcp_gateway import MCPGateway, MCPRequest
    from .files import MAX_INPUT_BYTES, InputFile, input_archive, parse_artifacts, parse_completion
except ImportError:  # uvicorn on the independent node
    from mcp_gateway import MCPGateway, MCPRequest
    from files import MAX_INPUT_BYTES, InputFile, input_archive, parse_artifacts, parse_completion

LIMITS = {
    "timeout_seconds": 30,
    "memory_mb": 256,
    "cpu": 1,
    "pids": 64,
    "workspace_mb": 16,
    "output_bytes": 32768,
    "max_code_chars": 20000,
}
TERMINAL = {"completed", "failed", "cancelled", "timed_out", "output_limit"}


class Execution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    run_id: UUID
    code: str = Field(min_length=1, max_length=20000)
    protocol: Literal[1, 2] = 1
    inputs: list[InputFile] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def bounded_inputs(self):
        import base64

        if self.protocol == 1 and self.inputs:
            raise ValueError("File inputs require protocol 2")
        if len({item.name for item in self.inputs}) != len(self.inputs):
            raise ValueError("Duplicate input filenames")
        if (
            sum(len(base64.b64decode(item.content_base64)) for item in self.inputs)
            > MAX_INPUT_BYTES
        ):
            raise ValueError("Input quota exceeded")
        return self


def container_spec(image, code, run_id, job_id):
    if not image.startswith("sha256:") or len(image) != 71:
        raise ValueError("Runner must be pinned to a local image digest")
    return {
        "Image": image,
        "User": "65532:65532",
        "WorkingDir": "/work",
        "Entrypoint": ["python", "-I", "-B", "-c"],
        "Cmd": [code],
        "Env": ["PYTHONDONTWRITEBYTECODE=1", "PYTHONUNBUFFERED=1", "LANG=C.UTF-8"],
        "NetworkDisabled": True,
        "OpenStdin": False,
        "Tty": False,
        "Labels": {
            "agent.sandbox": "v1",
            "agent.run": str(run_id),
            "agent.job": str(job_id),
        },
        "HostConfig": {
            "Runtime": "runsc",
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "Memory": 256 * 1024**2,
            "MemorySwap": 256 * 1024**2,
            "NanoCpus": 1000000000,
            "PidsLimit": 64,
            "OomKillDisable": False,
            "IpcMode": "none",
            "Tmpfs": {
                "/work": "rw,noexec,nosuid,nodev,size=16m,mode=1777",
                "/tmp": "rw,noexec,nosuid,nodev,size=8m,mode=1777",
            },
            "Ulimits": [
                {"Name": "nofile", "Soft": 128, "Hard": 128},
                {"Name": "core", "Soft": 0, "Hard": 0},
            ],
            "LogConfig": {
                "Type": "json-file",
                "Config": {"max-size": "128k", "max-file": "1"},
            },
            "RestartPolicy": {"Name": "no"},
            "AutoRemove": False,
        },
    }


class Engine:
    def __init__(self, socket="/var/run/docker.sock"):
        self.probe_until = 0.0
        self.probe_lock = asyncio.Lock()
        self.http = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(uds=socket),
            base_url="http://docker/v1.45",
            timeout=8,
        )

    async def request(self, method, path, **kwargs):
        response = await self.http.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else None

    async def ready(self, image):
        info = await self.request("GET", "/info")
        if "runsc" not in info.get("Runtimes", {}):
            raise RuntimeError("gVisor runtime unavailable")
        inspected = await self.request("GET", f"/images/{image}/json")
        if inspected["Id"] != image:
            raise RuntimeError("Runner image mismatch")

    async def probe(self, image):
        await self.ready(image)
        async with self.probe_lock:
            if self.probe_until > time.monotonic():
                return
            job_id = uuid4()
            name = "agent-code-" + str(job_id)
            try:
                await self.ensure(
                    name,
                    container_spec(
                        image,
                        "import os, pathlib, numpy, pandas, matplotlib; assert os.getuid() == 65532; assert pathlib.Path('/opt/agent-runner.py').is_file(); print('sandbox-ready')",
                        job_id,
                        job_id,
                    ),
                )
                async with asyncio.timeout(8):
                    while True:
                        info = await self.inspect(name)
                        if not info["State"].get("Running"):
                            if info["State"].get("ExitCode") != 0:
                                raise RuntimeError("Runtime self-test failed")
                            break
                        await asyncio.sleep(0.1)
                self.probe_until = time.monotonic() + 15
            finally:
                await self.remove(name)

    async def inspect(self, name):
        try:
            return await self.request("GET", f"/containers/{name}/json")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    async def ensure(self, name, spec):
        if await self.inspect(name) is None:
            try:
                await self.request("POST", "/containers/create", params={"name": name}, json=spec)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 409:
                    raise
        info = await self.inspect(name)
        # Names alone are not trusted when reconciling after a crash.
        if info["Config"].get("Labels") != spec["Labels"] or info["Image"] != spec["Image"]:
            raise RuntimeError("Container identity mismatch")
        actual = info.get("HostConfig", {})
        for key in (
            "Runtime",
            "NetworkMode",
            "ReadonlyRootfs",
            "Privileged",
            "CapDrop",
            "SecurityOpt",
            "Memory",
            "MemorySwap",
            "NanoCpus",
            "PidsLimit",
            "Tmpfs",
        ):
            if actual.get(key) != spec["HostConfig"].get(key):
                raise RuntimeError("Container security configuration mismatch")
        if (
            actual.get("Binds")
            or actual.get("Devices")
            or info["Config"].get("User") != spec["User"]
        ):
            raise RuntimeError("Unexpected container access")
        expected_mounts = spec["HostConfig"].get("Mounts", [])
        actual_mounts = info.get("Mounts", [])
        if len(actual_mounts) != len(expected_mounts):
            raise RuntimeError(f"Container mount mismatch expected={[(m.get('Type'),m.get('Source'),m.get('Target'),m.get('ReadOnly')) for m in expected_mounts]} actual={[(m.get('Type'),m.get('Name'),m.get('Source'),m.get('Destination'),m.get('RW')) for m in actual_mounts]}")
        for expected, mounted in zip(expected_mounts, actual_mounts):
            source = str(mounted.get("Source", ""))
            expected_source = str(expected.get("Source", ""))
            if (
                mounted.get("Type") != expected.get("Type")
                or mounted.get("Destination") != expected.get("Target")
                or bool(mounted.get("RW", not mounted.get("ReadOnly", False))) != (not expected.get("ReadOnly", False))
                or not (source == expected_source or source.endswith("/" + expected_source + "/_data"))
            ):
                raise RuntimeError(f"Container mount mismatch item={mounted.get('Type')}:{mounted.get('Source')}:{mounted.get('Destination')}:{mounted.get('RW')} expected={expected.get('Type')}:{expected.get('Source')}:{expected.get('Target')}:{expected.get('ReadOnly')}")
        if (
            info["Config"].get("Entrypoint") != spec["Entrypoint"]
            or info["Config"].get("Cmd") != spec["Cmd"]
        ):
            raise RuntimeError("Container command mismatch")
        if info["State"]["Status"] == "created":
            await self.request("POST", f"/containers/{name}/start")

    async def stop(self, name):
        info = await self.inspect(name)
        if info and info["State"].get("Paused"):
            await self.request("POST", f"/containers/{name}/unpause")
        if info and info["State"].get("Running"):
            try:
                await self.request("POST", f"/containers/{name}/kill", params={"signal": "SIGKILL"})
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in (404, 409):
                    raise
        info = await self.inspect(name)
        if info and info["State"].get("Running"):
            raise RuntimeError("Container has not stopped")

    async def remove(self, name):
        try:
            await self.request(
                "DELETE", f"/containers/{name}", params={"force": "true", "v": "true"}
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise

    async def logs(self, name):
        # Docker non-TTY logs are multiplexed: 8-byte header + frame payload.
        raw = bytearray()
        cut = False
        async with self.http.stream(
            "GET",
            f"/containers/{name}/logs",
            params={"stdout": "true", "stderr": "true"},
        ) as response:
            response.raise_for_status()
            async for block in response.aiter_bytes():
                remaining = LIMITS["output_bytes"] + 8192 - len(raw)
                raw.extend(block[:remaining])
                if len(block) >= remaining:
                    cut = True
                    break
        result = decode_logs(bytes(raw))
        result["truncated"] = result["truncated"] or cut
        return result

    async def archive(self, name, path, limit):
        raw = bytearray()
        async with self.http.stream(
            "GET", f"/containers/{name}/archive", params={"path": path}
        ) as response:
            if response.status_code == 404:
                return None
            response.raise_for_status()
            async for block in response.aiter_bytes():
                if len(raw) + len(block) > limit:
                    raise ValueError("File transfer limit exceeded")
                raw.extend(block)
        return bytes(raw)

    async def pause(self, name):
        await self.request("POST", f"/containers/{name}/pause")
        info = await self.inspect(name)
        if not info or not info["State"].get("Paused"):
            raise RuntimeError("Unable to freeze execution")

    async def stage_inputs(self, image, body, output_volume=None):
        """Copy bounded files into a volume using a container that never starts."""
        volume, name = "agent-input-" + str(body.id), "agent-stage-" + str(body.id)
        await self.remove(name)
        await self.remove_input_volume(body.id)
        await self.request(
            "POST",
            "/volumes/create",
            json={
                "Name": volume,
                "Labels": {
                    "agent.sandbox": "v2-input",
                    "agent.job": str(body.id),
                    "agent.created": str(time.time()),
                },
            },
        )
        spec = container_spec(image, "", body.run_id, body.id)
        # Staging runs as root solely to make the mounted volumes writable by the
        # unprivileged runner (Docker volumes are initialized with root ownership).
        spec["User"] = "0:0"
        spec["HostConfig"]["Mounts"] = [
            {"Type": "volume", "Source": volume, "Target": "/inputs", "ReadOnly": False}
        ]
        if output_volume:
            spec["HostConfig"]["Mounts"].append({"Type": "volume", "Source": output_volume, "Target": "/outputs", "ReadOnly": False})
        spec["Labels"]["agent.phase"] = "input-staging"
        try:
            spec["Entrypoint"] = ["sh", "-c"]
            spec["Cmd"] = ["chmod 0777 /inputs /outputs 2>/dev/null || true; sleep 30"]
            await self.request("POST", "/containers/create", params={"name": name}, json=spec)
            await self.request("POST", f"/containers/{name}/start")
            response = await self.http.put(
                f"/containers/{name}/archive",
                params={"path": "/inputs"},
                content=input_archive(body.inputs),
                headers={"Content-Type": "application/x-tar"},
            )
            response.raise_for_status()
            if output_volume:
                import base64, hashlib
                init = InputFile(name="agent-output-init", content_base64=base64.b64encode(b"init").decode(), sha256=hashlib.sha256(b"init").hexdigest())
                response = await self.http.put(f"/containers/{name}/archive", params={"path": "/outputs"}, content=input_archive([init]), headers={"Content-Type": "application/x-tar"})
                response.raise_for_status()
        finally:
            await self.remove(name)

    async def create_output_volume(self, job_id):
        name = "agent-output-" + str(job_id)
        try:
            await self.request("POST", "/volumes/create", json={
                "Name": name,
                "Labels": {"agent.sandbox": "v2-output", "agent.job": str(job_id), "agent.created": str(time.time())},
            })
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 409:
                raise
        return name

    async def remove_output_volume(self, job_id):
        try:
            await self.request("DELETE", "/volumes/agent-output-" + str(job_id))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise

    async def remove_input_volume(self, job_id):
        try:
            await self.request("DELETE", "/volumes/agent-input-" + str(job_id))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise


def decode_logs(raw):
    streams = {1: bytearray(), 2: bytearray()}
    pos, total, clipped = 0, 0, False
    while pos + 8 <= len(raw):
        channel = raw[pos]
        size = int.from_bytes(raw[pos + 4 : pos + 8], "big")
        pos += 8
        count = min(size, max(0, LIMITS["output_bytes"] - total))
        if channel in streams:
            streams[channel].extend(raw[pos : pos + count])
        total += count
        if size > count or pos + size > len(raw):
            clipped = True
            break
        pos += size
    decoded = {
        "stdout": streams[1].decode("utf-8", errors="replace"),
        "stderr": streams[2].decode("utf-8", errors="replace"),
    }
    remaining = LIMITS["output_bytes"]
    for key in ("stdout", "stderr"):
        encoded = decoded[key].encode("utf-8")
        if len(encoded) > remaining:
            decoded[key] = encoded[:remaining].decode("utf-8", errors="ignore")
            clipped = True
        remaining -= len(decoded[key].encode("utf-8"))
    return {**decoded, "truncated": clipped}


class Manager:
    def __init__(self, path, image, engine):
        self.image, self.engine = image, engine
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, hash TEXT NOT NULL, code TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL, result TEXT)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS cancelled_runs (run_id TEXT PRIMARY KEY, created REAL NOT NULL)"
        )
        if "request_json" not in {row[1] for row in self.db.execute("PRAGMA table_info(jobs)")}:
            self.db.execute("ALTER TABLE jobs ADD COLUMN request_json TEXT")
        self.db.commit()
        self.tasks = {}
        self.slots = asyncio.Semaphore(max(1, int(os.environ.get("SANDBOX_CONCURRENCY", "2"))))
        self.lifecycle = asyncio.Lock()

    def row(self, job_id):
        return self.db.execute("SELECT * FROM jobs WHERE id=?", (str(job_id),)).fetchone()

    def cancelled(self, run_id):
        return (
            self.db.execute(
                "SELECT 1 FROM cancelled_runs WHERE run_id=?", (str(run_id),)
            ).fetchone()
            is not None
        )

    def save(self, job_id, state, result):
        self.db.execute(
            "UPDATE jobs SET state=?, result=?, code='', request_json=NULL WHERE id=?",
            (state, json.dumps(result), str(job_id)),
        )
        self.db.commit()

    def start(self, job_id):
        if str(job_id) not in self.tasks:
            task = asyncio.create_task(self.execute(str(job_id)))
            self.tasks[str(job_id)] = task
            task.add_done_callback(lambda done: self.tasks.pop(str(job_id), None))

    async def submit(self, body):
        serialized = body.model_dump_json()
        digest = hashlib.sha256(
            (serialized if body.protocol == 2 else body.code).encode()
        ).hexdigest()
        async with self.lifecycle:
            row = self.row(body.id)
            if row:
                if row["hash"] != digest or row["run_id"] != str(body.run_id):
                    raise HTTPException(409, "Execution identity conflict")
                return self.public(row)
            if self.cancelled(body.run_id):
                raise HTTPException(409, "Run cancelled")
            await self.engine.probe(self.image) if body.protocol == 2 else await self.engine.ready(
                self.image
            )
            if (
                self.db.execute(
                    "SELECT COUNT(*) FROM jobs WHERE state NOT IN ('completed','failed','cancelled','timed_out','output_limit')"
                ).fetchone()[0]
                >= 16
            ):
                raise HTTPException(429, "Execution queue full")
            if self.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] >= 2000:
                raise HTTPException(429, "Execution history capacity reached")
            if (
                self.db.execute(
                    "SELECT COALESCE(SUM(LENGTH(result)),0)+COALESCE(SUM(LENGTH(request_json)),0) FROM jobs"
                ).fetchone()[0]
                > 256 * 1024**2
            ):
                raise HTTPException(429, "Execution storage capacity reached")
            self.db.execute(
                "INSERT INTO jobs(id,run_id,hash,code,state,created,result,request_json) VALUES(?,?,?,?,?,?,NULL,?)",
                (
                    str(body.id),
                    str(body.run_id),
                    digest,
                    body.code,
                    "queued",
                    time.time(),
                    serialized if body.protocol == 2 else None,
                ),
            )
            self.db.commit()
            self.start(body.id)
            return self.public(self.row(body.id))

    def public(self, row):
        return {
            "id": row["id"],
            "run_id": row["run_id"],
            "state": row["state"],
            "result": json.loads(row["result"]) if row["result"] else None,
        }

    async def execute(self, job_id):
        if self.row(job_id)["request_json"]:
            return await self.execute_files(job_id)
        name = "agent-code-" + job_id
        async with self.slots:
            row = self.row(job_id)
            try:
                async with self.lifecycle:
                    if row["state"] in TERMINAL:
                        return
                    if self.cancelled(row["run_id"]):
                        await self.engine.stop(name)
                        self.save(job_id, "cancelled", {})
                        return
                    if time.time() - row["created"] > LIMITS["timeout_seconds"]:
                        await self.engine.stop(name)
                        self.save(job_id, "timed_out", {})
                        return
                    await self.engine.ready(self.image)
                    if row["state"] == "running" and await self.engine.inspect(name) is None:
                        self.save(
                            job_id,
                            "failed",
                            {"error": "Execution state lost; automatic re-execution refused"},
                        )
                        return
                    await self.engine.ensure(
                        name,
                        container_spec(self.image, row["code"], row["run_id"], job_id),
                    )
                    self.db.execute("UPDATE jobs SET state='running' WHERE id=?", (job_id,))
                    self.db.commit()
                deadline = min(row["created"] + 60, time.time() + LIMITS["timeout_seconds"])
                reason = None
                while True:
                    info = await self.engine.inspect(name)
                    if info is None:
                        raise RuntimeError("Execution container missing")
                    if not info["State"].get("Running"):
                        break
                    if self.cancelled(row["run_id"]):
                        reason = "cancelled"
                    elif time.time() >= deadline:
                        reason = "timed_out"
                    else:
                        output = await self.engine.logs(name)
                        if output["truncated"]:
                            reason = "output_limit"
                    if reason:
                        await self.engine.stop(name)
                        break
                    await asyncio.sleep(0.3)
                output = await self.engine.logs(name)
                info = await self.engine.inspect(name)
                output.update(
                    exit_code=info["State"].get("ExitCode"),
                    oom_killed=bool(info["State"].get("OOMKilled")),
                )
                reason = reason or (
                    "cancelled"
                    if self.cancelled(row["run_id"])
                    else "output_limit"
                    if output["truncated"]
                    else "completed"
                    if output["exit_code"] == 0
                    else "failed"
                )
                self.save(job_id, reason, output)
            except asyncio.CancelledError:
                # On control-plane shutdown, leave state for reconciliation. Container TTL
                # is also enforced by the node sweeper (see deployment instructions).
                raise
            except Exception:
                # Never declare a terminal result until actual execution has stopped.
                try:
                    await self.engine.stop(name)
                    self.save(
                        job_id,
                        "cancelled" if self.cancelled(row["run_id"]) else "failed",
                        {"error": "Isolated execution failed"},
                    )
                except Exception:
                    pass  # Persist running state; maintenance reconciles it later.
            finally:
                if self.row(job_id)["state"] in TERMINAL:
                    with suppress(Exception):
                        await self.engine.remove(name)

    async def execute_files(self, job_id):
        name = "agent-code-" + job_id
        async with self.slots:
            row = self.row(job_id)
            try:
                async with asyncio.timeout(
                    max(0.001, row["created"] + LIMITS["timeout_seconds"] - time.time())
                ):
                    async with self.lifecycle:
                        if row["state"] in TERMINAL:
                            return
                        if self.cancelled(row["run_id"]):
                            await self.engine.stop(name)
                            self.save(job_id, "cancelled", {})
                            return
                        if time.time() >= row["created"] + LIMITS["timeout_seconds"]:
                            await self.engine.stop(name)
                            self.save(job_id, "timed_out", {})
                            return
                        body = Execution.model_validate_json(row["request_json"])
                        await self.engine.ready(self.image)
                        existing = await self.engine.inspect(name)
                        if row["state"] == "running" and existing is None:
                            raise RuntimeError("Execution state lost")
                        output_volume = await self.engine.create_output_volume(body.id) if hasattr(self.engine, "create_output_volume") else None
                        if existing is None:
                            await self.engine.stage_inputs(self.image, body, output_volume)
                        spec = container_spec(self.image, body.code, body.run_id, body.id)
                        spec["Entrypoint"] = ["python", "-I", "-B", "/opt/agent-runner.py"]
                        spec["HostConfig"]["Memory"] = spec["HostConfig"]["MemorySwap"] = (
                            512 * 1024**2
                        )
                        spec["HostConfig"]["Mounts"] = [
                            {
                                "Type": "volume",
                                "Source": "agent-input-" + job_id,
                                "Target": "/inputs",
                                "ReadOnly": True,
                            }
                        ]
                        if output_volume:
                            spec["HostConfig"]["Mounts"].append({"Type": "volume", "Source": output_volume, "Target": "/work/outputs", "ReadOnly": False})
                        spec["Env"] += [
                            "MPLBACKEND=Agg",
                            "MPLCONFIGDIR=/tmp/matplotlib",
                            "OPENBLAS_NUM_THREADS=1",
                            "OMP_NUM_THREADS=1",
                        ]
                        await self.engine.ensure(name, spec)
                        self.db.execute("UPDATE jobs SET state='running' WHERE id=?", (job_id,))
                        self.db.commit()
                    reason, completion, artifacts, artifact_error = None, None, [], None
                    while True:
                        info = await self.engine.inspect(name)
                        if not info or not info["State"].get("Running"):
                            raise RuntimeError("Execution exited without completion record")
                        output = await self.engine.logs(name)
                        if self.cancelled(body.run_id):
                            reason = "cancelled"
                        elif time.time() >= row["created"] + LIMITS["timeout_seconds"]:
                            reason = "timed_out"
                        elif output["truncated"]:
                            reason = "output_limit"
                        if reason:
                            break
                        marker = await self.engine.archive(
                            name, "/work/outputs/.execution-result.json", 16384
                        )
                        if marker is not None:
                            # Freeze all child processes before reading the completion and outputs.
                            if not info["State"].get("Paused"):
                                await self.engine.pause(name)
                            completion = parse_completion(
                                await self.engine.archive(
                                    name, "/work/outputs/.execution-result.json", 16384
                                )
                            )
                            if completion["exit_code"] == 0:
                                try:
                                    raw = await self.engine.archive(
                                        name, "/work/outputs", 5 * 1024**2
                                    )
                                    artifacts = parse_artifacts(raw or b"", root_name="outputs")
                                except Exception:
                                    # Artifact failure is explicit; never publish a partial bundle.
                                    artifacts, artifact_error = (
                                        [],
                                        "Artifact collection rejected or unavailable",
                                    )
                            reason = (
                                "completed"
                                if completion["exit_code"] == 0 and not artifact_error
                                else "failed"
                            )
                            break
                        await asyncio.sleep(0.3)
                    await self.engine.stop(name)
                    info = await self.engine.inspect(name)
                    output = await self.engine.logs(name)
                    if self.cancelled(body.run_id):
                        reason, artifacts = "cancelled", []
                    elif output["truncated"]:
                        reason, artifacts = "output_limit", []
                    output.update(
                        exit_code=completion["exit_code"]
                        if completion
                        else info["State"].get("ExitCode"),
                        oom_killed=bool(info["State"].get("OOMKilled")),
                        artifacts=artifacts,
                        artifact_error=artifact_error,
                    )
                    self.save(job_id, reason, output)
            except asyncio.CancelledError:
                raise
            except Exception:
                try:
                    logging.getLogger("sandbox.manager").exception("file execution failed")
                    await self.engine.stop(name)
                    info = await self.engine.inspect(name)
                    output = await self.engine.logs(name) if info else {}
                    output.update(
                        error="File execution failed",
                        artifacts=[],
                        oom_killed=bool(info and info["State"].get("OOMKilled")),
                    )
                    self.save(
                        job_id,
                        "cancelled"
                        if self.cancelled(row["run_id"])
                        else "timed_out"
                        if time.time() >= row["created"] + LIMITS["timeout_seconds"]
                        else "failed",
                        output,
                    )
                except Exception:
                    pass
            finally:
                if self.row(job_id)["state"] in TERMINAL:
                    with suppress(Exception):
                        await self.engine.remove(name)
                        await self.engine.remove("agent-stage-" + job_id)
                        await self.engine.remove_input_volume(job_id)
                        if hasattr(self.engine, "remove_output_volume"):
                            await self.engine.remove_output_volume(job_id)

    async def cancel(self, run_id):
        async with self.lifecycle:
            self.db.execute(
                "INSERT OR IGNORE INTO cancelled_runs VALUES(?,?)",
                (str(run_id), time.time()),
            )
            self.db.commit()
            rows = self.db.execute("SELECT * FROM jobs WHERE run_id=?", (str(run_id),)).fetchall()
            for row in rows:
                await self.engine.stop("agent-code-" + row["id"])
                if row["state"] not in TERMINAL:
                    self.save(row["id"], "cancelled", {})
            return {"stopped": True}

    async def maintain(self):
        while True:
            rows = self.db.execute("SELECT id,state,created FROM jobs LIMIT 2000").fetchall()
            for row in rows:
                if row["state"] not in TERMINAL:
                    self.start(row["id"])
                else:
                    try:
                        await self.engine.remove("agent-code-" + row["id"])
                        await self.engine.remove("agent-stage-" + row["id"])
                        if hasattr(self.engine, "remove_input_volume"):
                            await self.engine.remove_input_volume(row["id"])
                        if hasattr(self.engine, "remove_output_volume"):
                            await self.engine.remove_output_volume(row["id"])
                    except Exception:
                        continue
                    if row["created"] < time.time() - 8 * 86400:
                        self.db.execute("DELETE FROM jobs WHERE id=?", (row["id"],))
            self.db.execute(
                "DELETE FROM cancelled_runs WHERE created<?", (time.time() - 8 * 86400,)
            )
            self.db.commit()
            await asyncio.sleep(5)


def create_app(manager=None, token=None):
    secret = token or os.environ.get("SANDBOX_TOKEN", "")
    if len(secret) < 32:
        raise RuntimeError("SANDBOX_TOKEN must contain at least 32 characters")
    runner = manager or Manager(
        os.environ.get("SANDBOX_DATABASE", "/data/jobs.db"),
        os.environ.get("SANDBOX_IMAGE", ""),
        Engine(),
    )
    mcp_gateway = MCPGateway(runner, os.environ.get("SANDBOX_MCP_IMAGE", ""), container_spec)

    async def auth(credential: HTTPAuthorizationCredentials = Security(HTTPBearer())):
        if not hmac.compare_digest(credential.credentials, secret):
            raise HTTPException(401, "Unauthorized")

    @asynccontextmanager
    async def lifespan(app):
        janitor = asyncio.create_task(runner.maintain())
        try:
            yield
        finally:
            janitor.cancel()
            tasks = list(runner.tasks.values())
            for task in tasks:
                task.cancel()
            await asyncio.gather(janitor, *tasks, return_exceptions=True)

    app = FastAPI(
        lifespan=lifespan,
        dependencies=[Depends(auth)],
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    class BoundedBody:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http" or scope["method"] != "POST":
                return await self.app(scope, receive, send)
            chunks, size = [], 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                size += len(message.get("body", b""))
                if size > 8 * 1024**2:
                    from starlette.responses import JSONResponse

                    return await JSONResponse({"detail": "Request too large"}, status_code=413)(
                        scope, receive, send
                    )
                chunks.append(message)
                if not message.get("more_body"):
                    break

            async def replay():
                return chunks.pop(0) if chunks else await receive()

            await self.app(scope, replay, send)

    app.add_middleware(BoundedBody)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        from starlette.responses import JSONResponse

        return JSONResponse({"detail": "Invalid or oversized request"}, status_code=422)

    @app.get("/mcp/health")
    async def mcp_health():
        return await mcp_gateway.health()

    @app.post("/mcp/exchange")
    async def mcp_exchange(body: MCPRequest):
        return {"result": await mcp_gateway.execute(body)}

    @app.get("/health")
    async def health():
        try:
            await runner.engine.probe(runner.image)
        except Exception:
            raise HTTPException(503, "Isolated runtime unavailable") from None
        return {
            "status": "ready",
            "protocol": 1,
            "max_protocol": 2,
            "file_execution": {
                "input_bytes": MAX_INPUT_BYTES,
                "artifact_total_bytes": 4 * 1024**2,
                "artifact_file_bytes": 2 * 1024**2,
                "max_files": 10,
                "memory_mb": 512,
                "inputs_read_only": True,
            },
            "runtime": "runsc",
            "image": runner.image,
            "network": "none",
            "limits": LIMITS,
        }

    @app.post("/executions", status_code=202)
    async def submit(body: Execution):
        try:
            return await runner.submit(body)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "Isolated runtime unavailable") from None

    @app.get("/executions/{job_id}")
    async def result(job_id: UUID):
        row = runner.row(job_id)
        if not row:
            raise HTTPException(404, "Execution not found")
        return runner.public(row)

    @app.delete("/runs/{run_id}")
    async def cancel(run_id: UUID):
        try:
            result = await runner.cancel(run_id)
            await mcp_gateway.cancel(run_id)
            return result
        except Exception:
            raise HTTPException(503, "Unable to confirm execution stopped") from None

    return app
