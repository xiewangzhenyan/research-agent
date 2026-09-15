"""Fixed client inside gVisor. User commands never run in the manager process."""

import asyncio
import json
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def exchange(body):
    params = StdioServerParameters(
        command=body["command"], args=body["args"], env=body["env"], cwd="/work"
    )
    # Server stderr can contain credentials; never forward it to the control plane.
    with open(os.devnull, "w") as errors:
        async with stdio_client(params, errlog=errors) as streams:
            async with ClientSession(*streams) as session:
                info = await session.initialize()
                if body["operation"] == "call":
                    value = (await session.call_tool(body["name"], body["arguments"])).model_dump(
                        mode="json", by_alias=True
                    )
                else:
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
                            raise ValueError("Too many tools")
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
                    if len({t["name"] for t in tools}) != len(tools):
                        raise ValueError("Duplicate tools")
                    value = {"tools": tools, "resources": resources, "prompts": prompts}
                if len(json.dumps(value).encode()) > 30000:
                    raise ValueError("Result too large")
                return value


async def main():
    try:
        body = json.loads(os.environ.pop("AGENT_MCP_REQUEST"))
        async with asyncio.timeout(20):
            result = {"ok": True, "result": await exchange(body)}
    except Exception:
        result = {"ok": False}
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
