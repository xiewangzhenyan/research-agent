"""Live enhancement checks. Creates disposable accounts only in an isolated review DB.

For release smoke checks, --fixtures accepts previously created disposable accounts.
Credentials stay in a mode-0600 fixture file; stdout contains only check results.
"""

import argparse
import asyncio
import json
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pymupdf
import websockets

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.db.models.user import User
from app.db.session import get_db_context
from app.schemas.knowledge import RetrievalConfig


def fixture_pdf():
    with pymupdf.open() as doc:
        for text in [
            "青岚计划出差管理办法。住宿费用适用标准见下一页。本文为软件功能验收用合成资料。",
            "每人每晚最高可报销620元,超出部分由个人承担。申请时必须附上有效发票。",
            "归档完成后保留电子回执,备查期限为三年。",
        ]:
            doc.new_page().insert_text((50, 100), text, fontname="china-s", fontsize=11)
        return doc.tobytes()


async def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--fixtures", type=Path)
    args = parser.parse_args()
    path = args.fixtures or Path("/tmp/rerank-context-fixtures.json")
    if args.fixtures:
        users = json.loads(path.read_text())
    else:
        assert settings.POSTGRES_DB.endswith("_review")
        users = []
        async with get_db_context() as db:
            for i in range(2):
                password = secrets.token_urlsafe(24)
                user = User(
                    email=f"rerank-check-{int(time.time())}-{i}@example.com",
                    full_name="增强检索验收",
                    hashed_password=get_password_hash(password),
                    onboarding_completed_at=datetime.now(UTC),
                )
                db.add(user)
                await db.flush()
                users.append({"id": str(user.id), "email": user.email, "password": password})
    for user in users:
        user["token"] = create_access_token(user["id"])
    path.write_text(json.dumps(users))
    path.chmod(0o600)
    a, b = users
    async with httpx.AsyncClient(
        base_url="http://localhost:38001/api/v1/knowledge", timeout=60
    ) as client:

        async def req(method, url, user=a, **kw):
            return await client.request(
                method, url, headers={"Authorization": "Bearer " + user["token"]}, **kw
            )

        async def ready(kb):
            for _ in range(180):
                rows = (await req("GET", f"/bases/{kb}/documents")).json()
                if rows and all(d["status"] == "ready" for d in rows):
                    return rows
                assert not any(d["status"] == "failed" for d in rows), rows
                await asyncio.sleep(0.5)
            raise AssertionError("Index timeout")

        defaults = RetrievalConfig().model_dump()
        assert (await req("GET", "/retrieval-config", user=b)).json() == defaults
        kb = (await req("POST", "/bases", json={"name": "增强检索验收"})).json()["id"]
        a["base_id"] = kb
        path.write_text(json.dumps(users))
        response = await req(
            "POST", f"/bases/{kb}/documents", files={"file": ("context-policy.pdf", fixture_pdf())}
        )
        assert response.status_code == 201, response.text
        did = response.json()["id"]
        await ready(kb)
        a["document_id"] = did
        query = "青岚计划"
        config = defaults | {"mode": "keyword", "result_limit": 1}
        body = {
            "knowledge_base_ids": [kb],
            "document_ids": [did],
            "query": query,
            "diagnostics": True,
            "retrieval_config": config,
        }
        baseline = (await req("POST", "/search", json=body)).json()
        assert len(baseline["items"]) == 1 and baseline["items"][0]["page"] == 1, baseline
        assert "620" not in baseline["items"][0]["content"]
        enhanced = config | {"rerank_enabled": True, "context_enabled": True}
        response = await req("POST", "/search", json=body | {"retrieval_config": enhanced})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["diagnostics"]["rerank"]["status"] == "applied", result
        assert [x["page"] for x in result["items"]] == [1, 2], result
        assert (
            result["items"][1]["score_type"] == "context" and "620" in result["items"][1]["content"]
        )
        assert all("embedding" not in x for x in result["items"])
        assert (
            await req("POST", "/search", json=body | {"retrieval_config": enhanced}, user=b)
        ).status_code == 404
        assert (await req("PUT", "/retrieval-config", json=enhanced)).status_code == 200
        assert (await req("GET", "/retrieval-config", user=b)).json() == defaults
        assert (await req("GET", "/retrieval-config")).json() == enhanced
        print(
            "Real PDF indexing; baseline lacks amount; enhanced search adds page 2 independently; local rerank applied; account isolation and settings: PASS",
            flush=True,
        )

        captured = {}
        async with websockets.connect(
            "ws://localhost:38001/api/v1/ws/agent",
            subprotocols=["access_token." + a["token"], "chat"],
        ) as ws:
            await ws.send(
                json.dumps(
                    {
                        "message": "青岚计划的住宿标准是什么?",
                        "knowledge_base_ids": [kb],
                        "knowledge_document_ids": [did],
                    }
                )
            )
            async with asyncio.timeout(150):
                while True:
                    event = json.loads(await ws.recv())
                    kind, data = event["type"], event["data"]
                    assert kind != "error", data
                    if kind == "conversation_created":
                        captured["conversation_id"] = data["conversation_id"]
                    elif kind == "tool_result":
                        captured["retrieval"] = json.loads(data["content"])
                    elif kind == "final_result":
                        captured["answer"] = data["output"]
                    elif kind == "complete":
                        break
        assert "620" in captured["answer"], captured
        ranking = captured["retrieval"]["retrieval"]["ranking"]
        assert ranking["config"]["context_enabled"] and ranking["rerank"]["status"] == "applied", (
            captured
        )
        sources = captured["retrieval"]["items"]
        source = next(s for s in sources if s["page"] == 2)
        sid = source["citation_id"]
        citation = (await req("GET", f"/citations/{sid}")).json()
        assert citation["page"] == 2 and citation["quotes"], citation
        assert all(q in citation["content"] for q in citation["quotes"]), citation
        assert (await req("GET", f"/citations/{sid}", user=b)).status_code == 404
        a.update(citation_id=sid, conversation_id=captured["conversation_id"])
        path.write_text(json.dumps(users))
        print(
            "Real generated answer uses saved enhancements; 620 amount has literal page-2 quote; cross-account citation denied: PASS",
            flush=True,
        )
        original_generation = result["items"][0]["index_generation"]
        assert (await req("POST", f"/documents/{did}/retry")).status_code == 200
        await ready(kb)
        rerun = (await req("POST", "/search", json=body | {"retrieval_config": enhanced})).json()
        assert all(s["index_generation"] != original_generation for s in rerun["items"]), rerun
        assert len({s["index_generation"] for s in rerun["items"]}) == 1
        retained = (await req("GET", f"/citations/{sid}")).json()
        assert retained["state"] == "reindexed" and retained["content"] == citation["content"]
        print(
            "Reindex replaces all retrieved generations together; historical page citation retains its original snapshot: PASS",
            flush=True,
        )
        # Keep the owned fixture for browser review; caller deletes its base and users afterward.


if __name__ == "__main__":
    asyncio.run(main())
