"""Official MCP SDK behind account-scoped, DNS-pinned HTTP transport."""

import asyncio
import ipaddress
import json
import re
import socket
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

from app.core.exceptions import BadRequestError, ExternalServiceError
from app.services.capability_assets import unseal


def validate_url(value):
    try:
        url = urlsplit(value)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.fragment
            or url.query
        ):
            raise ValueError("url")
        if url.port is not None and not 1 <= url.port <= 65535:
            raise ValueError("port")
    except ValueError as exc:
        raise BadRequestError(
            message="请填写 HTTP(S) 地址；认证信息请放在请求头中，地址不支持查询参数"
        ) from exc
    return url


def validate_secrets(transport, values):
    for name, value in values.items():
        if (
            not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,99}", name)
            or len(value) > 8000
            or any(c in value for c in ("\r", "\n", "\x00"))
        ):
            raise BadRequestError(message="请求头或环境变量格式无效")
        if transport != "stdio" and name.lower() in (
            "host",
            "content-length",
            "connection",
            "transfer-encoding",
            "cookie",
            "proxy-authorization",
        ):
            raise BadRequestError(message="此请求头不能由用户覆盖")


async def public_address(host, port):
    rows = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(r[4][0] for r in rows))
    if not addresses or any(
        not ipaddress.ip_address(a).is_global or ipaddress.ip_address(a).is_multicast
        for a in addresses
    ):
        raise BadRequestError(message="MCP 地址必须解析到公网；内网、回环和云元数据地址不可访问")
    return addresses[0]


class LimitedStream(httpx.AsyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    async def __aiter__(self):
        size = 0
        async for chunk in self.stream:
            size += len(chunk)
            if size > 4 * 1024 * 1024:
                raise BadRequestError(message="MCP 响应超过大小限制")
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class PublicTransport(httpx.AsyncHTTPTransport):
    def __init__(self, origin):
        super().__init__(retries=0, limits=httpx.Limits(max_connections=4), trust_env=False)
        self.origin = httpx.URL(origin)

    async def handle_async_request(self, request):
        url = request.url
        if (url.scheme, url.host, url.port) != (
            self.origin.scheme,
            self.origin.host,
            self.origin.port,
        ):
            raise BadRequestError(message="MCP 服务不能将认证请求转发到其他地址")
        address = await public_address(url.host, url.port or (443 if url.scheme == "https" else 80))
        # Connect to the validated IP; TLS verification still uses the original hostname.
        request.extensions["sni_hostname"] = url.host
        request.headers["host"] = url.netloc.decode()
        request.headers["accept-encoding"] = "identity"
        request.url = url.copy_with(host=address)
        try:
            response = await super().handle_async_request(request)
        finally:
            request.url = url
        if response.headers.get("content-encoding", "identity").lower() not in ("identity", ""):
            await response.aclose()
            raise BadRequestError(message="MCP 服务未遵守无压缩请求，响应已拒绝")
        if response.status_code in (301, 302, 303, 307, 308):
            await response.aclose()
            raise BadRequestError(message="MCP 地址发生重定向，请填写最终服务地址")
        response.stream = LimitedStream(response.stream)
        return response


async def exchange(asset, operation="discover", *, name=None, arguments=None, run_id=None):
    config = asset.config
    if config["transport"] == "stdio":
        from app.services import mcp_sandbox

        env = unseal(asset)
        validate_secrets("stdio", env)
        return await mcp_sandbox.exchange(
            config, env, operation=operation, name=name, arguments=arguments, run_id=run_id
        )
    url = config["url"]
    validate_url(url)
    headers = unseal(asset)
    if headers and not url.startswith("https://"):
        raise BadRequestError(message="携带认证信息的 MCP 连接必须使用 HTTPS")
    validate_secrets(config["transport"], headers)

    def client_factory(**kwargs):
        return httpx.AsyncClient(
            headers=kwargs.get("headers"),
            timeout=httpx.Timeout(20, connect=5),
            follow_redirects=False,
            trust_env=False,
            transport=PublicTransport(url),
        )

    transport = sse_client if config["transport"] == "sse" else streamablehttp_client
    try:
        async with asyncio.timeout(25):
            async with transport(
                url,
                headers=headers,
                timeout=5,
                sse_read_timeout=20,
                httpx_client_factory=client_factory,
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    info = await session.initialize()
                    if operation == "call":
                        result = await session.call_tool(name, arguments or {})
                        value = result.model_dump(mode="json", by_alias=True)
                        if len(json.dumps(value)) > 64000:
                            raise BadRequestError(message="工具结果过大，请缩小查询范围")
                        return value
                    tools, resources, prompts = [], [], []
                    if info.capabilities.tools:
                        cursor = None
                        for _ in range(5):
                            page = await session.list_tools(cursor)
                            tools.extend(
                                t.model_dump(mode="json", by_alias=True) for t in page.tools
                            )
                            cursor = page.nextCursor
                            if not cursor:
                                break
                        if cursor or len(tools) > 100:
                            raise BadRequestError(
                                message="单个 MCP 连接最多发现 100 个工具，请在服务端缩小工具范围"
                            )
                    if info.capabilities.resources:
                        resources = [
                            r.model_dump(mode="json", by_alias=True)
                            for r in (await session.list_resources()).resources
                        ][:50]
                    if info.capabilities.prompts:
                        prompts = [
                            p.model_dump(mode="json", by_alias=True)
                            for p in (await session.list_prompts()).prompts
                        ][:50]
                    value = {"tools": tools, "resources": resources, "prompts": prompts}
                    if len({t["name"] for t in tools}) != len(tools):
                        raise BadRequestError(message="MCP 服务返回了重复工具名称，请修正后重试")
                    if len(json.dumps(value)) > 250000:
                        raise BadRequestError(message="MCP 工具说明过大，请减少服务端工具")
                    return value
    except BadRequestError:
        raise
    except Exception as exc:
        # SDK task groups may wrap upstream errors including secret headers or URLs.
        raise ExternalServiceError(
            message="MCP 连接失败：请检查地址、认证信息和协议，或稍后重试"
        ) from exc


async def test_connection(service, asset_id, revision):
    asset = await service.get(asset_id, write=True)
    service.check_revision(asset, revision)
    if asset.kind != "mcp":
        raise BadRequestError(message="此能力不是 MCP 连接")
    try:
        catalog = await exchange(asset)
        known = {t["name"] for t in catalog["tools"]}
        asset.config = {
            **asset.config,
            "enabled_tools": [n for n in asset.config["enabled_tools"] if n in known],
            "auto_approved_tools": [n for n in asset.config["auto_approved_tools"] if n in known],
        }
        asset.catalog, asset.status, asset.status_message = (
            catalog,
            "ready",
            "连接成功，已刷新能力列表",
        )
    except (BadRequestError, ExternalServiceError) as exc:
        asset.status, asset.status_message = "unavailable", exc.message
    asset.tested_at = datetime.now(UTC).isoformat()
    asset.revision += 1
    await service.audit(asset, "connection_tested")
    await service.db.flush()
    await service.db.refresh(asset)
    return service.public(asset, detail=True)
