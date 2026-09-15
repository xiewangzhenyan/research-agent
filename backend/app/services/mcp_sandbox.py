"""Validated independent Stdio runtime; no local subprocess fallback."""

import hashlib
import time
from uuid import uuid4

from app.core.config import settings
from app.core.exceptions import BadRequestError, ExternalServiceError
from app.services import sandbox_client

_health_cache = None


async def health():
    global _health_cache
    if not sandbox_client.configured() or not settings.SANDBOX_MCP_IMAGE_ID:
        return {"status": "not_configured"}
    key = (
        settings.SANDBOX_URL,
        hashlib.sha256(settings.SANDBOX_TOKEN.encode()).hexdigest(),
        settings.SANDBOX_MCP_IMAGE_ID,
    )
    if _health_cache and _health_cache[0] == key and _health_cache[1] > time.monotonic():
        return _health_cache[2]
    result = {"status": "unavailable"}
    try:
        data = await sandbox_client.request("GET", "/mcp/health", timeout=35)
        if (
            data.get("status") == "ready"
            and data.get("protocol") == 1
            and data.get("runtime") == "runsc"
            and data.get("network") == "none"
            and data.get("image") == settings.SANDBOX_MCP_IMAGE_ID
        ):
            result = {"status": "ready"}
    except ExternalServiceError:
        pass
    _health_cache = (key, time.monotonic() + 15, result)
    return result


async def exchange(config, env, *, operation, name, arguments, run_id=None):
    if config["command"] not in ("python", "python3", "/usr/local/bin/python"):
        raise BadRequestError(
            message="当前隔离镜像支持 Python 与 MCP SDK；不支持 npx/uvx 或在线安装。联网服务请使用 HTTP/SSE。"
        )
    if (await health())["status"] != "ready":
        raise BadRequestError(message="隔离 MCP 执行节点暂不可用或正在执行其他任务，请稍后重试")
    data = await sandbox_client.request(
        "POST",
        "/mcp/exchange",
        {
            "run_id": str(run_id or uuid4()),
            "command": config["command"],
            "args": config.get("args", []),
            "env": env,
            "operation": operation,
            "name": name,
            "arguments": arguments or {},
        },
        timeout=45,
        response_limit=64000,
    )
    if not isinstance(data.get("result"), dict):
        raise ExternalServiceError(message="MCP 沙箱结果格式无效")
    return data["result"]
