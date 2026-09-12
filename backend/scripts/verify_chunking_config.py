"""Review-only verification of actual config application, ownership and in-flight snapshots."""

import asyncio
import hashlib
import json
import secrets
import threading
import time
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.db.models.knowledge import KnowledgeDocument
from app.db.models.user import User
from app.db.session import get_db_context
from app.services.file_storage import get_file_storage
from app.worker.tasks import knowledge as tasks


async def main():
    assert settings.POSTGRES_DB.endswith("_review")
    users = []
    async with get_db_context() as db:
        for n in range(2):
            password = secrets.token_urlsafe(18)
            user = User(
                email=f"config-{int(time.time())}-{n}@example.com",
                full_name="配置验收",
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

        async def base(name):
            r = await req("POST", "/knowledge/bases", json={"name": name})
            assert r.status_code == 201, r.text
            return r.json()["id"]

        async def ready(kb):
            for _ in range(120):
                rows = (await req("GET", f"/knowledge/bases/{kb}/documents")).json()
                if rows and all(d["status"] == "ready" for d in rows):
                    return rows[0]
                assert not any(d["status"] == "failed" for d in rows), rows
                await asyncio.sleep(0.5)
            raise AssertionError("Indexing timed out")

        kb = await base("通用知识库配置验收")
        small = {"chunk_size": 300, "chunk_overlap": 0}
        large = {"chunk_size": 420, "chunk_overlap": 40}
        path = f"/knowledge/bases/{kb}/chunking-config"
        assert (await req("PUT", path, json=small, user=b)).status_code == 404
        assert (
            await req("PUT", path, json={"chunk_size": 256, "chunk_overlap": 128})
        ).status_code == 422
        assert (await req("PUT", path, json=small)).status_code == 200
        text = "通用验收资料：住宿上限为620元。此数字仅用于功能验证。" * 50
        raw = text.encode()
        r = await req(
            "POST", f"/knowledge/bases/{kb}/documents", files={"file": ("settings.txt", raw)}
        )
        assert r.status_code == 201, r.text
        did = r.json()["id"]
        document = await ready(kb)
        assert document["chunking_config"] == small, document
        chunks = (await req("GET", f"/knowledge/documents/{did}/chunks")).json()["items"]
        assert "".join(c["content"] for c in chunks) == text and all(
            len(c["content"]) <= 300 for c in chunks
        )
        assert (await req("PUT", path, json=large)).status_code == 200
        assert (await ready(kb))["chunking_config"] == small
        r = await req("POST", f"/knowledge/documents/{did}/retry")
        assert r.json()["status"] == "pending" and r.json()["chunking_config"] is None, r.text
        assert (await ready(kb))["chunking_config"] == large
        chunks = (await req("GET", f"/knowledge/documents/{did}/chunks")).json()["items"]
        assert all(len(c["content"]) <= 420 for c in chunks)
        assert all(x["content"][-40:] == y["content"][:40] for x, y in pairwise(chunks))
        print(
            "Owner-only validated config, actual chunk lengths/overlap, retained old index and reprocessing: PASS",
            flush=True,
        )
        # Freeze embedding to change configuration after this job has captured it.
        frozen = await base("处理中配置快照验收")
        assert (
            await req("PUT", f"/knowledge/bases/{frozen}/chunking-config", json=small)
        ).status_code == 200
        storage_path = await get_file_storage().save(a["id"], "frozen.txt", raw)
        async with get_db_context() as db:
            doc = KnowledgeDocument(
                knowledge_base_id=UUID(frozen),
                filename="frozen.txt",
                storage_path=storage_path,
                size=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
                status="pending",
            )
            db.add(doc)
            await db.flush()
            fid = doc.id
        started, release = threading.Event(), threading.Event()
        original = tasks.embed

        def paused(texts):
            started.set()
            if not release.wait(30):
                raise RuntimeError("Test release timeout")
            return original(texts)

        tasks.embed = paused
        pending = asyncio.create_task(tasks.process_document(fid))
        try:
            async with asyncio.timeout(20):
                while not started.is_set():
                    await asyncio.sleep(0.02)
            assert (
                await req("PUT", f"/knowledge/bases/{frozen}/chunking-config", json=large)
            ).status_code == 200
            release.set()
            await pending
        finally:
            release.set()
            tasks.embed = original
            if not pending.done():
                await pending
        async with get_db_context() as db:
            doc = await db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == fid))
            assert doc.status == "ready" and doc.chunking_config == small
        print(
            "Config changed during embedding cannot alter the running job snapshot: PASS",
            flush=True,
        )
        search = (
            await req(
                "POST",
                "/knowledge/search",
                json={"knowledge_base_ids": [kb], "query": "住宿上限是多少？"},
            )
        ).json()
        assert search["items"] and all(h["chunking_config"] == large for h in search["items"]), (
            search
        )
        a.update(base_id=kb, document_id=did)
        p = Path("/tmp/core-config-fixtures.json")
        p.write_text(json.dumps(users))
        p.chmod(0o600)


if __name__ == "__main__":
    asyncio.run(main())
