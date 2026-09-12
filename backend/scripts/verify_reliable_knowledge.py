"""After verify_native_knowledge.py, verify real model answers and citation lifecycle.

Requires an isolated review backend, worker and configured generation model.
"""

import asyncio
import json
from pathlib import Path

import httpx
import websockets


async def main():
    from app.core.config import settings

    assert settings.POSTGRES_DB.endswith("_review"), "Use a disposable database ending in _review"
    a, b = json.loads(Path("/tmp/native-fixtures.json").read_text())
    async with httpx.AsyncClient(base_url="http://localhost:38001/api/v1", timeout=100) as client:

        async def req(method, path, user=a, **kw):
            return await client.request(
                method, path, headers={"Authorization": "Bearer " + user["token"]}, **kw
            )

        async def turn(payload, expect_error=False):
            async with websockets.connect(
                "ws://localhost:38001/api/v1/ws/agent",
                subprotocols=["access_token." + a["token"], "chat"],
            ) as ws:
                await ws.send(json.dumps(payload))
                result = {"sources": [], "cid": payload.get("conversation_id")}
                async with asyncio.timeout(125):
                    while True:
                        e = json.loads(await ws.recv())
                        t = e["type"]
                        d = e["data"]
                        if t == "error":
                            if expect_error:
                                return d
                            raise AssertionError(d)
                        if t == "conversation_created":
                            result["cid"] = d["conversation_id"]
                        if t == "tool_result":
                            result["sources"] += json.loads(d["content"]).get("items", [])
                        if t == "final_result":
                            result["answer"] = d["output"]
                        if t == "message_saved":
                            result["mid"] = d["message_id"]
                        if t == "complete":
                            return result

        result = await turn(
            {"message": "星河项目的住宿报销上限是多少？", "knowledge_base_ids": [a["base_id"]]}
        )
        assert "650" in result["answer"] and result["sources"], result
        cid = result["cid"]
        a["conversation_id"] = cid
        config = (await req("GET", f"/conversations/{cid}")).json()
        assert (
            config["active_knowledge_base_ids"] == [a["base_id"]]
            and config["knowledge_strict"] is True
        ), config
        source = result["sources"][0]
        sid = source["citation_id"]
        r = await req("GET", f"/knowledge/citations/{sid}")
        detail = r.json()
        assert (
            r.status_code == 200
            and detail["state"] == "current"
            and len(detail["file_version"]) == 64
            and "650" in detail["content"]
        ), detail
        assert (await req("GET", f"/knowledge/citations/{sid}", user=b)).status_code == 404
        messages = (await req("GET", f"/conversations/{cid}/messages")).json()
        stored = json.loads(
            next(
                t["result"]
                for m in messages["items"]
                if m["role"] == "assistant"
                for t in m["tool_calls"]
                if t["tool_name"] == "search_knowledge_base"
            )
        )
        assert stored["items"][0]["content"] == "" and stored["items"][0]["citation_id"] == sid
        print(
            "Strict answer, owned structured citation, file fingerprint, atomic pointer persistence: PASS",
            flush=True,
        )
        result2 = await turn({"message": "那最晚什么时候提交申请？", "conversation_id": cid})
        assert "15" in result2["answer"] and result2["sources"], result2
        print(
            "Conversation settings restored without client selection; context-aware follow-up: PASS",
            flush=True,
        )
        unknown = await turn({"message": "星河项目总经理的薪资是多少？", "conversation_id": cid})
        assert not unknown["sources"] and "未找到足够依据" in unknown["answer"], unknown
        over = await turn({"message": "问" * 1501, "conversation_id": cid}, True)
        assert "1500" in over["message"]
        r = await req(
            "PATCH",
            f"/conversations/{cid}",
            json={"active_knowledge_base_ids": [str(__import__("uuid").uuid4())]},
        )
        assert r.status_code == 404, r.text
        print(
            "Insufficient evidence abstention, explicit long-query rejection, invalid scope rejection: PASS",
            flush=True,
        )
        await req("POST", f"/knowledge/documents/{a['document_id']}/retry")
        detail = (await req("GET", f"/knowledge/citations/{sid}")).json()
        assert detail["state"] == "reindexed" and "650" in detail["content"]
        # Keep fixture for browser verification; deletion verification uses a dedicated second document below.
        kb = (await req("POST", "/knowledge/bases", json={"name": "引用删除验证"})).json()["id"]
        document = (
            await req(
                "POST",
                f"/knowledge/bases/{kb}/documents",
                files={"file": ("删除验证.txt", "玄武系统的服务编码为 DELETE7251。".encode())},
            )
        ).json()["id"]
        assert document
        for _ in range(100):
            docs = (await req("GET", f"/knowledge/bases/{kb}/documents")).json()
            if docs[0]["status"] == "ready":
                break
            await asyncio.sleep(0.5)
        dresult = await turn({"message": "玄武系统的服务编码是什么？", "knowledge_base_ids": [kb]})
        assert dresult["sources"], dresult
        dsid = dresult["sources"][0]["citation_id"]
        assert (await req("DELETE", f"/knowledge/bases/{kb}")).status_code == 204
        tombstone = (await req("GET", f"/knowledge/citations/{dsid}")).json()
        assert tombstone == {"state": "deleted", "title": "原文已删除", "content": ""}, tombstone
        err = await turn({"message": "再说一次", "conversation_id": dresult["cid"]}, True)
        assert "知识库" in err["message"]
        msgs = (await req("GET", f"/conversations/{dresult['cid']}/messages")).json()
        assert all(
            "DELETE7251" not in (tc.get("result") or "")
            for m in msgs["items"]
            for tc in m["tool_calls"]
        )
        print(
            "Reindex snapshot retained; deletion scrubs citations; deleted scope never silently widens: PASS",
            flush=True,
        )
        a["citation_id"] = sid
        Path("/tmp/native-fixtures.json").write_text(json.dumps([a, b]))
        Path("/tmp/native-fixtures.json").chmod(0o600)


asyncio.run(main())
