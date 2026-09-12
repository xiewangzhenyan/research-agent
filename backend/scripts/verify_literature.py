"""Disposable review-only integration of document scope and citation reading.

Creates synthetic fixtures, runs the configured model and retains fixtures for browser checks.
Remove the isolated database/media after verification.
"""

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


async def main():
    assert settings.POSTGRES_DB.endswith("_review")
    users = []
    async with get_db_context() as db:
        for n in range(2):
            password = secrets.token_urlsafe(18)
            user = User(
                email=f"literature-{int(time.time())}-{n}@example.com",
                full_name=f"文献验收{n}",
                hashed_password=get_password_hash(password),
                onboarding_completed_at=datetime.now(UTC),
            )
            db.add(user)
            await db.flush()
            users.append(
                {
                    "id": str(user.id),
                    "email": user.email,
                    "password": password,
                    "token": create_access_token(user.id),
                }
            )
    a, b = users
    async with httpx.AsyncClient(base_url="http://localhost:38001/api/v1", timeout=90) as client:

        async def req(method, path, user=a, **kw):
            return await client.request(
                method, path, headers={"Authorization": "Bearer " + user["token"]}, **kw
            )

        async def base(name, user=a):
            r = await req("POST", "/knowledge/bases", user=user, json={"name": name})
            assert r.status_code == 201, r.text
            return r.json()["id"]

        async def upload(kb, name, raw, user=a):
            r = await req(
                "POST", f"/knowledge/bases/{kb}/documents", user=user, files={"file": (name, raw)}
            )
            assert r.status_code == 201, r.text
            return r.json()["id"]

        async def ready(kb, user=a):
            for _ in range(120):
                rows = (await req("GET", f"/knowledge/bases/{kb}/documents", user=user)).json()
                if all(d["status"] == "ready" for d in rows):
                    return
                assert not any(d["status"] == "failed" for d in rows), rows
                await asyncio.sleep(0.5)
            raise AssertionError("indexing timeout")

        async def turn(payload, expect_error=False):
            result = {"cid": payload.get("conversation_id")}
            async with websockets.connect(
                "ws://localhost:38001/api/v1/ws/agent",
                subprotocols=["access_token." + a["token"], "chat"],
            ) as ws:
                await ws.send(json.dumps(payload))
                async with asyncio.timeout(130):
                    while True:
                        event = json.loads(await ws.recv())
                        t = event["type"]
                        d = event["data"]
                        if t == "error":
                            if expect_error:
                                return d
                            raise AssertionError(d)
                        if t == "conversation_created":
                            result["cid"] = d["conversation_id"]
                        if t == "final_result":
                            result["answer"] = d["output"]
                        if t == "tool_result":
                            result["retrieval"] = json.loads(d["content"])
                        if t == "message_saved":
                            result["mid"] = d["message_id"]
                        if t == "complete":
                            return result

        kb = await base("科研文献验收")
        other = await base("范围外资料")
        foreign = await base("另一账号资料", b)
        pdf = pymupdf.open()
        texts = [
            "Synthetic LSPR study A. This is a generated regression fixture, not a real scientific paper. The introduction describes calibration and optical sensing.",
            "Synthetic LSPR study A: refractive-index sensitivity is 125 nm/RIU. Measurement wavelength range is 500 to 700 nm.",
            "Synthetic LSPR study A. This concluding passage describes calibration limitations. All values in this file are artificial test data.",
        ]
        for text in texts:
            pdf.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 750), text, fontsize=12)
        raw = pdf.tobytes()
        pdf.close()
        doc_a = await upload(kb, "LSPR-study-A.pdf", raw)
        doc_b = await upload(
            kb,
            "LSPR-study-B.txt",
            "合成测试文献 B：LSPR 折射率灵敏度为 310 nm/RIU。这是虚构验收资料，不代表实际研究结论。".encode(),
        )
        outside = await upload(other, "outside.txt", "范围外测试文献：灵敏度 999 nm/RIU。".encode())
        secret = await upload(
            foreign, "private.txt", "另一账号合成资料：灵敏度 888 nm/RIU。".encode(), b
        )
        await ready(kb)
        await ready(other)
        await ready(foreign, b)
        payload = {
            "knowledge_base_ids": [kb],
            "query": "折射率灵敏度是多少？",
            "document_ids": [doc_a],
        }
        search = (await req("POST", "/knowledge/search", json=payload)).json()
        assert "refractive index sensitivity" in search["terminology"]["aliases"]
        hits = search["items"]
        assert (
            hits
            and all(h["document_id"] == doc_a for h in hits)
            and any("125" in h["content"] for h in hits)
        ), hits
        for selection, code in [([doc_a, secret], 404), ([outside], 404), ([], 422)]:
            r = await req("POST", "/knowledge/search", json=payload | {"document_ids": selection})
            assert r.status_code == code, (r.status_code, r.text)
        result = await turn(
            {
                "message": "折射率灵敏度是多少？",
                "knowledge_base_ids": [kb],
                "knowledge_document_ids": [doc_a],
            }
        )
        assert "125" in result["answer"] and "310" not in result["answer"], result
        metadata = result["retrieval"]["retrieval"]
        assert metadata["original_query"] == "折射率灵敏度是多少？"
        assert "refractive index sensitivity" in metadata["terminology"]["aliases"]
        sources = result["retrieval"]["items"]
        assert sources and all(s["document_id"] == doc_a for s in sources)
        sid = sources[0]["citation_id"]
        cid = result["cid"]
        config = (await req("GET", f"/conversations/{cid}")).json()
        assert config["active_knowledge_document_ids"] == [doc_a]
        source = (await req("GET", f"/knowledge/citations/{sid}")).json()
        assert source["quotes"] and all(q in source["content"] for q in source["quotes"])
        context = (await req("GET", f"/knowledge/citations/{sid}/context")).json()
        assert (
            context["state"] == "current"
            and 1 <= len(context["items"]) <= 3
            and any(c["cited"] for c in context["items"])
        ), context
        assert source["preview_url"].endswith("#page=2"), source
        for path in [f"/knowledge/citations/{sid}", f"/knowledge/citations/{sid}/context"]:
            assert (await req("GET", path, user=b)).status_code == 404
        messages = (await req("GET", f"/conversations/{cid}/messages")).json()["items"]
        persisted = json.loads(
            next(
                tc["result"] for m in messages if m["role"] == "assistant" for tc in m["tool_calls"]
            )
        )
        assert persisted["items"][0]["content"] == "" and "quotes" not in persisted["items"][0]
        print(
            "Scoped PDF search excludes other papers and accounts; live answer 125, exact quote and page 2 context: PASS",
            flush=True,
        )
        follow = await turn({"message": "那测量波长范围是多少？", "conversation_id": cid})
        assert "500" in follow["answer"] and "700" in follow["answer"], follow
        assert all(s["document_id"] == doc_a for s in follow["retrieval"]["items"])
        assert (
            await req(
                "PATCH", f"/conversations/{cid}", json={"active_knowledge_document_ids": [secret]}
            )
        ).status_code == 404
        assert (
            await req("PATCH", f"/conversations/{cid}", json={"active_knowledge_base_ids": []})
        ).status_code == 400
        print(
            "Document scope persists across follow-ups; foreign documents and invalid scope changes rejected: PASS",
            flush=True,
        )
        unknown = await turn(
            {
                "message": "局域表面等离激元共振传感器的采购报价是多少？",
                "knowledge_base_ids": [kb],
                "knowledge_document_ids": [doc_a],
            }
        )
        assert not unknown["retrieval"]["items"], unknown
        assert unknown["retrieval"]["retrieval"]["terminology"]["aliases"]
        print("Bilingual aliases do not turn related passages into a supported price: PASS", flush=True)
        result_b = await turn(
            {
                "message": "LSPR 折射率灵敏度是多少？",
                "knowledge_base_ids": [kb],
                "knowledge_document_ids": [doc_b],
            }
        )
        assert "310" in result_b["answer"] and "125" not in result_b["answer"], result_b
        sid_b = result_b["retrieval"]["items"][0]["citation_id"]
        await req("POST", f"/knowledge/documents/{doc_b}/retry")
        changed = (await req("GET", f"/knowledge/citations/{sid_b}/context")).json()
        assert changed["state"] == "reindexed" and not changed["items"], changed
        retained = (await req("GET", f"/knowledge/citations/{sid_b}")).json()
        assert retained["quotes"]
        await req("DELETE", f"/knowledge/documents/{doc_b}")
        deleted = (await req("GET", f"/knowledge/citations/{sid_b}/context")).json()
        assert deleted["state"] == "deleted" and not deleted["items"]
        err = await turn({"message": "再次回答", "conversation_id": result_b["cid"]}, True)
        assert "文献" in err["message"], err
        print(
            "Changing selected paper yields 310; reindex context stays separate; deleted selection fails closed: PASS",
            flush=True,
        )
        a.update(base_id=kb, document_id=doc_a, conversation_id=cid, citation_id=sid)
        Path("/tmp/literature-fixtures.json").write_text(json.dumps(users))
        Path("/tmp/literature-fixtures.json").chmod(0o600)


asyncio.run(main())
