"""Isolated API verification: previews do not ingest; confirmation pins owned settings."""

import asyncio
import json
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

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
                email=f"preview-{int(time.time())}-{n}@example.com",
                full_name="分块预览验收",
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

        async def ready(base):
            for _ in range(120):
                docs = (await req("GET", f"/bases/{base}/documents")).json()
                if docs and all(d["status"] == "ready" for d in docs):
                    return docs[0]
                assert not any(d["status"] == "failed" for d in docs), docs
                await asyncio.sleep(0.5)
            raise AssertionError("Index timeout")

        r = await req("POST", "/bases", json={"name": "分块预览API验收"})
        assert r.status_code == 201, r.text
        base = r.json()["id"]
        path = f"/bases/{base}"
        raw = ("通用验收资料:住宿上限为620元。" * 80).encode()
        files = {"file": ("guide.txt", raw)}
        small = {"chunk_size": 300, "chunk_overlap": 0}
        large = {"chunk_size": 420, "chunk_overlap": 40}
        assert (
            await req("POST", path + "/preview", files=files, data=small, user=b)
        ).status_code == 404
        assert (
            await req(
                "POST",
                path + "/preview",
                files=files,
                data={"chunk_size": 256, "chunk_overlap": 128},
            )
        ).status_code == 400
        assert (
            await req("POST", path + "/preview", files={"file": ("empty.txt", b" ")})
        ).status_code == 400
        media_before = sorted(str(p) for p in Path("/app/media").rglob("*") if p.is_file())
        response = await req("POST", path + "/preview", files=files, data=small)
        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["chunking_config"] == small
        assert (await req("GET", path + "/documents")).json() == []
        assert media_before == sorted(str(p) for p in Path("/app/media").rglob("*") if p.is_file())
        data = {"preview_token": preview["preview_token"]}
        assert (
            await req("POST", path + "/documents", files=files, data=data, user=b)
        ).status_code == 404
        assert (
            await req(
                "POST",
                path + "/documents",
                files={"file": ("guide.txt", raw + b"changed")},
                data=data,
            )
        ).status_code == 400
        other = (await req("POST", "/bases", json={"name": "另一知识库"})).json()["id"]
        assert (
            await req("POST", f"/bases/{other}/documents", files=files, data=data)
        ).status_code == 400
        assert (await req("PUT", path + "/chunking-config", json=large)).status_code == 200
        uploaded = await req("POST", path + "/documents", files=files, data=data)
        assert uploaded.status_code == 201, uploaded.text
        assert uploaded.json()["chunking_config"] is None
        document = await ready(base)
        assert document["chunking_config"] == small, document
        items = (await req("GET", f"/documents/{document['id']}/chunks")).json()["items"]
        assert [{k: v for k, v in item.items() if k != "id"} for item in items] == preview["items"]
        assert (await req("POST", path + "/documents", files=files, data=data)).status_code == 400
        search = await req(
            "POST", "/search", json={"knowledge_base_ids": [base], "query": "住宿上限"}
        )
        assert search.status_code == 200 and search.json()["items"], search.text
        print(
            "Preview without stored files/documents; account/base/file isolation; confirmed index equals preview despite settings changes; searchable: PASS",
            flush=True,
        )
        assert (await req("POST", f"/documents/{document['id']}/retry")).status_code == 200
        assert (await ready(base))["chunking_config"] == large
        print(
            "Explicit reprocessing uses current base settings; duplicate confirmation is reported without silent parameter substitution: PASS",
            flush=True,
        )
        a["base_id"] = base
        fixture = Path("/tmp/core-preview-fixtures.json")
        fixture.write_text(json.dumps(users))
        fixture.chmod(0o600)


asyncio.run(main())
