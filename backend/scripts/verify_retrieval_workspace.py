"""Review-only live API/index checks for account defaults and temporary experiments."""

import asyncio
import json
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.db.models.user import User
from app.db.session import get_db_context
from app.schemas.knowledge import RetrievalConfig
from app.services.knowledge import KnowledgeService


async def main():
    assert settings.POSTGRES_DB.endswith("_review")
    users = []
    async with get_db_context() as db:
        for i in range(2):
            password = secrets.token_urlsafe(18)
            user = User(
                email=f"retrieval-{int(time.time())}-{i}@example.com",
                full_name="检索验收",
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
    async with httpx.AsyncClient(
        base_url="http://localhost:38001/api/v1/knowledge", timeout=60
    ) as client:

        async def req(method, path, user=a, **kw):
            return await client.request(
                method, path, headers={"Authorization": "Bearer " + user["token"]}, **kw
            )

        defaults = RetrievalConfig().model_dump()
        assert (await req("GET", "/retrieval-config")).json() == defaults
        keyword = defaults | {"mode": "keyword", "result_limit": 3}
        assert (await req("PUT", "/retrieval-config", json=keyword)).status_code == 200
        assert (await req("GET", "/retrieval-config", user=b)).json() == defaults
        assert (
            await req(
                "PUT",
                "/retrieval-config",
                json=defaults | {"semantic_weight": 0, "keyword_weight": 0},
            )
        ).status_code == 422
        kb = (await req("POST", "/bases", json={"name": "通用检索API验收"})).json()["id"]
        raw = "编号,说明\nPOLICY620,住宿上限620元\nPOLICY180,交通上限180元".encode()
        response = await req("POST", f"/bases/{kb}/documents", files={"file": ("policy.csv", raw)})
        assert response.status_code == 201, response.text
        for _ in range(120):
            docs = (await req("GET", f"/bases/{kb}/documents")).json()
            if docs and docs[0]["status"] == "ready":
                break
            assert not any(d["status"] == "failed" for d in docs), docs
            await asyncio.sleep(0.5)
        else:
            raise AssertionError("Index timeout")
        body = {"knowledge_base_ids": [kb], "query": "POLICY620", "diagnostics": True}
        result = (await req("POST", "/search", json=body)).json()
        assert result["diagnostics"]["config"] == keyword, result
        assert result["diagnostics"]["embedding_ms"] == 0
        assert result["items"][0]["score_type"] == "bm25" and "620" in result["items"][0]["content"]
        assert (await req("POST", "/search", json=body, user=b)).status_code == 404
        assert (await req("GET", f"/documents/{docs[0]['id']}/chunks", user=b)).status_code == 404
        override = defaults | {"mode": "semantic", "semantic_threshold": 0.99}
        trial = (await req("POST", "/search", json=body | {"retrieval_config": override})).json()
        assert trial["diagnostics"]["config"] == override
        assert trial["diagnostics"]["keyword_candidates"] == 0
        assert (await req("GET", "/retrieval-config")).json() == keyword
        # Same no-override service invocation as knowledge chat, with saved account defaults.
        async with get_db_context() as db:
            hits = await KnowledgeService(db, UUID(a["id"])).search([UUID(kb)], "POLICY620")
        assert hits and hits[0]["score_type"] == "bm25"
        assert (await req("POST", "/search", json=body | {"document_ids": []})).status_code == 422
        assert (
            await req("GET", "/citations/00000000-0000-0000-0000-000000000000")
        ).status_code == 404
        print(
            "Account-isolated persistent settings; owned retrieval; temporary overrides; keyword mode without query embedding; same saved defaults used by chat service: PASS",
            flush=True,
        )
        assert (await req("PUT", "/retrieval-config", json=defaults)).status_code == 200
        p = Path("/tmp/retrieval-workspace-fixtures.json")
        p.write_text(json.dumps(users))
        p.chmod(0o600)


asyncio.run(main())
