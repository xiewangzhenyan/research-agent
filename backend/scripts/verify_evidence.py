"""Review-only integration for multi-page evidence, scope and citation deletion."""

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

QUESTION = "LSPR study A 的折射率灵敏度、测量波长范围和孵育时间分别是多少？"


def fixture_pdf():
    with pymupdf.open() as doc:
        for text in [
            "LSPR study A. The refractive-index sensitivity is 151 nm/RIU.",
            "LSPR study A. The measurement wavelength range is 510 to 710 nm.",
            "LSPR study A. The incubation time is 18 minutes.",
        ]:
            page = doc.new_page()
            assert (
                page.insert_textbox(
                    pymupdf.Rect(50, 50, 550, 750),
                    text + " Synthetic test data, not scientific findings.",
                    fontsize=12,
                )
                >= 0
            )
        return doc.tobytes()


async def main():
    assert settings.POSTGRES_DB.endswith("_review")
    users = []
    async with get_db_context() as db:
        for n in range(2):
            password = secrets.token_urlsafe(18)
            user = User(
                email=f"evidence-{int(time.time())}-{n}@example.com",
                full_name="跨页依据验收",
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

        r = await req("POST", "/knowledge/bases", json={"name": "跨页证据验收"})
        assert r.status_code == 201, r.text
        kb = r.json()["id"]
        raw = fixture_pdf()
        r = await req(
            "POST", f"/knowledge/bases/{kb}/documents", files={"file": ("evidence-pages.pdf", raw)}
        )
        assert r.status_code == 201, r.text
        did = r.json()["id"]
        for _ in range(120):
            docs = (await req("GET", f"/knowledge/bases/{kb}/documents")).json()
            if docs and all(d["status"] == "ready" for d in docs):
                break
            assert not any(d["status"] == "failed" for d in docs), docs
            await asyncio.sleep(0.5)
        else:
            raise AssertionError("Indexing timed out")
        payload = {"knowledge_base_ids": [kb], "document_ids": [did], "query": QUESTION}
        r = await req("POST", "/knowledge/search", json=payload)
        assert r.status_code == 200, r.text
        hits = r.json()["items"]
        assert {h["page"] for h in hits} == {1, 2, 3}, hits
        assert all(h["document_id"] == did for h in hits)
        assert (await req("POST", "/knowledge/search", user=b, json=payload)).status_code == 404
        print(
            "Three adjacent PDF pages survive retrieval; foreign account is rejected: PASS",
            flush=True,
        )
        result = {}
        async with websockets.connect(
            "ws://localhost:38001/api/v1/ws/agent",
            subprotocols=["access_token." + a["token"], "chat"],
        ) as ws:
            await ws.send(
                json.dumps(
                    {
                        "message": QUESTION,
                        "knowledge_base_ids": [kb],
                        "knowledge_document_ids": [did],
                    }
                )
            )
            async with asyncio.timeout(130):
                while True:
                    event = json.loads(await ws.recv())
                    kind, data = event["type"], event["data"]
                    assert kind != "error", data
                    if kind == "conversation_created":
                        result["conversation_id"] = data["conversation_id"]
                    if kind == "final_result":
                        result["answer"] = data["output"]
                    if kind == "tool_result":
                        result["retrieval"] = json.loads(data["content"])
                    if kind == "complete":
                        break
        assert all(n in result["answer"] for n in ["151", "510", "710", "18"]), result
        sources = result["retrieval"]["items"]
        assert {s["page"] for s in sources} == {1, 2, 3}, sources
        for source in sources:
            path = f"/knowledge/citations/{source['citation_id']}"
            citation = (await req("GET", path)).json()
            assert citation["quotes"] and citation["preview_url"].endswith(
                f"#page={source['page']}"
            )
            assert all(q in citation["content"] for q in citation["quotes"])
            assert (await req("GET", path, user=b)).status_code == 404
        print(
            "Live answer uses all three pages with literal quotes and correct preview pages: PASS",
            flush=True,
        )
        # Retain a synthetic file and private account for final-image/browser checks.
        a.update(base_id=kb, document_id=did, conversation_id=result["conversation_id"])
        Path("/tmp/evidence-pages.pdf").write_bytes(raw)
        p = Path("/tmp/evidence-fixtures.json")
        p.write_text(json.dumps(users))
        p.chmod(0o600)


if __name__ == "__main__":
    asyncio.run(main())
