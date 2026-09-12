# ruff: noqa: RUF001
"""Authenticated bounded control-plane client; never executes code locally."""

import asyncio
import hashlib
import json
import time
from urllib.parse import urlsplit
from uuid import uuid5

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.services.sandbox_files import validate_artifacts

_health_cache = None


def configured():
    return bool(
        settings.SANDBOX_URL
        and len(settings.SANDBOX_TOKEN) >= 32
        and settings.SANDBOX_IMAGE_ID.startswith("sha256:")
    )


async def request(method, path, payload=None, timeout=8, response_limit=262144):
    if not configured():
        raise ExternalServiceError(message="代码沙箱尚未配置")
    url = settings.SANDBOX_URL.rstrip("/")
    parsed = urlsplit(url)
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not (
            parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname == "127.0.0.1")
        )
    ):
        raise ExternalServiceError(message="沙箱控制连接需要 HTTPS 或本机安全隧道")
    try:
        async with (
            httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False) as client,
            client.stream(
                method,
                url + path,
                json=payload,
                headers={"Authorization": f"Bearer {settings.SANDBOX_TOKEN}"},
            ) as response,
        ):
            response.raise_for_status()
            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > response_limit:
                    raise ValueError("Response limit exceeded")
            data = json.loads(chunks)
            if not isinstance(data, dict):
                raise ValueError("Expected an object response")
            return data
    except (httpx.HTTPError, ValueError) as exc:
        raise ExternalServiceError(
            message="隔离执行服务暂时不可用，未在业务服务器执行代码"
        ) from exc


async def health():
    global _health_cache
    if not configured():
        return {"status": "not_configured", "runtime": "gVisor", "network": "none"}
    key = (
        settings.SANDBOX_URL,
        hashlib.sha256(settings.SANDBOX_TOKEN.encode()).hexdigest(),
        settings.SANDBOX_IMAGE_ID,
    )
    if _health_cache and _health_cache[0] == key and _health_cache[1] > time.monotonic():
        return _health_cache[2]
    result = {"status": "unavailable", "runtime": "gVisor", "network": "none"}
    try:
        data = await request("GET", "/health", timeout=15)
        if (
            data.get("status") == "ready"
            and data.get("protocol") == 1
            and data.get("runtime") == "runsc"
            and data.get("network") == "none"
            and data.get("image") == settings.SANDBOX_IMAGE_ID
        ):
            result["status"] = "ready"
            capability = data.get("file_execution")
            if (
                data.get("max_protocol") == 2
                and isinstance(capability, dict)
                and capability.get("inputs_read_only") is True
            ):
                result["file_execution"] = {
                    "input_bytes": 5 * 1024**2,
                    "artifact_total_bytes": 4 * 1024**2,
                    "artifact_file_bytes": 2 * 1024**2,
                    "max_files": 10,
                    "memory_mb": 512,
                    "inputs_read_only": True,
                }
    except ExternalServiceError:
        pass
    _health_cache = (key, time.monotonic() + 15, result)
    return result


async def run_python(run_id, code, *, protocol=1, inputs=None):
    if protocol not in (1, 2) or (protocol == 1 and inputs):
        raise ExternalServiceError(message="沙箱文件协议无效")
    identity = (
        code
        if protocol == 1
        else json.dumps({"code": code, "inputs": inputs or [], "protocol": 2}, sort_keys=True)
    )
    job_id = uuid5(
        run_id,
        ("python:" if protocol == 1 else "python-files:")
        + hashlib.sha256(identity.encode()).hexdigest(),
    )
    payload = {"id": str(job_id), "run_id": str(run_id), "code": code}
    limit = 6 * 1024**2 if protocol == 2 else 262144
    if protocol == 2:
        payload.update(protocol=2, inputs=inputs or [])
    data = await request("POST", "/executions", payload, response_limit=limit)
    async with asyncio.timeout(75):
        while True:
            if data.get("id") != str(job_id) or data.get("run_id") != str(run_id):
                raise ExternalServiceError(message="沙箱执行记录不匹配")
            state = data.get("state")
            if state in {"completed", "failed", "cancelled", "timed_out", "output_limit"}:
                result = data.get("result") or {}
                if not isinstance(result, dict):
                    raise ExternalServiceError(message="沙箱结果格式无效")
                stdout, stderr = result.get("stdout", ""), result.get("stderr", "")
                if (
                    not isinstance(stdout, str)
                    or not isinstance(stderr, str)
                    or len((stdout + stderr).encode()) > 40000
                ):
                    raise ExternalServiceError(message="沙箱输出格式或大小无效")
                if state == "completed" and (
                    type(result.get("exit_code")) is not int
                    or result["exit_code"] != 0
                    or result.get("truncated")
                    or result.get("oom_killed")
                    or result.get("artifact_error")
                ):
                    raise ExternalServiceError(message="沙箱成功状态与执行结果不一致")
                files = (
                    validate_artifacts(result.get("artifacts", []), state) if protocol == 2 else []
                )
                return {
                    **({"artifact_files": files} if protocol == 2 else {}),
                    "error": "产物收集失败，未保存文件"
                    if result.get("artifact_error")
                    else "隔离执行失败"
                    if result.get("error")
                    else None,
                    "protocol": protocol,
                    "execution_id": str(job_id),
                    "state": state,
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": result.get("exit_code"),
                    "truncated": bool(result.get("truncated")),
                    "oom_killed": bool(result.get("oom_killed")),
                }
            if state not in {"queued", "running"}:
                raise ExternalServiceError(message="沙箱执行状态无效")
            await asyncio.sleep(0.5)
            data = await request("GET", f"/executions/{job_id}", response_limit=limit)


async def cancel_run(run_id):
    data = await request("DELETE", f"/runs/{run_id}")
    if data.get("stopped") is not True:
        raise ExternalServiceError(message="尚未确认沙箱已停止")
