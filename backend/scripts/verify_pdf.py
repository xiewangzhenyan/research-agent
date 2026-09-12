"""Disposable PDF pipeline/coverage verification; only runs against a review database."""

import asyncio
import json
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pymupdf
import websockets

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.db.models.knowledge import KnowledgeDocument
from app.db.models.user import User
from app.db.session import get_db_context
from app.services.knowledge import KnowledgeService
from app.worker.tasks.knowledge import set_stage


def fixture_pdf():
    with pymupdf.open() as doc:
        page = doc.new_page(width=600, height=800)
        for marker, x in [("RIGHT", 330), ("LEFT", 50)]:
            text = (
                f"{marker} COLUMN. Synthetic reading order fixture, not a scientific paper. "
                + (
                    "The refractive-index sensitivity is 142 nm/RIU. "
                    if marker == "LEFT"
                    else "This paragraph discusses artificial calibration limitations. "
                )
                + "This generated paragraph is long enough to form several lines in a column."
            )
            assert page.insert_textbox(pymupdf.Rect(x, 100, x + 220, 320), text, fontsize=11) >= 0
        doc.new_page()  # A truly blank page.
        page = doc.new_page()
        image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 3, 3))
        image.clear_with(180)
        page.insert_image(page.rect, pixmap=image, keep_proportion=False)
        page.insert_text((280, 800), "3")
        return doc.tobytes()


async def main():
    assert settings.POSTGRES_DB.endswith("_review")
    users = []
    async with get_db_context() as db:
        for n in range(2):
            password = secrets.token_urlsafe(18)
            user = User(
                email=f"pdf-{int(time.time())}-{n}@example.com",
                full_name="PDF 验收",
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

        async def req(method, path, user=a, **kwargs):
            r = await client.request(
                method, path, headers={"Authorization": "Bearer " + user["token"]}, **kwargs
            )
            return r

        async def ready(kb):
            for _ in range(120):
                r = await req("GET", f"/knowledge/bases/{kb}/documents")
                r.raise_for_status()
                rows = r.json()
                if rows and all(d["status"] == "ready" for d in rows):
                    return rows[0]
                assert not any(d["status"] == "failed" for d in rows), rows
                await asyncio.sleep(0.5)
            raise AssertionError("Indexing timed out")

        r = await req("POST", "/knowledge/bases", json={"name": "PDF 页面提取验收"})
        assert r.status_code == 201, r.text
        kb = r.json()["id"]
        raw = fixture_pdf()
        r = await req(
            "POST", f"/knowledge/bases/{kb}/documents", files={"file": ("mixed-columns.pdf", raw)}
        )
        assert r.status_code == 201, r.text
        did = r.json()["id"]
        doc = await ready(kb)
        report = doc["parse_report"]
        assert report["total_pages"] == 3 and report["text_pages"] == 2, report
        assert report["empty_text_pages"] == [2] and report["suspected_scan_pages"] == [3], report
        assert report["two_column_pages"] == [1], report
        chunks = (await req("GET", f"/knowledge/documents/{did}/chunks")).json()["items"]
        content = "\n".join(c["content"] for c in chunks)
        assert content.index("LEFT COLUMN") < content.index("RIGHT COLUMN"), content
        assert {c["page"] for c in chunks} == {1, 3}
        assert (await req("GET", f"/knowledge/bases/{kb}/documents", user=b)).status_code == 404
        print(
            "Mixed PDF: real two-column order, blank page and sparse image page report, account isolation: PASS",
            flush=True,
        )

        # Database-level stage update must reject old generations before writing reports.
        async with get_db_context() as db:
            guard = KnowledgeDocument(
                knowledge_base_id=UUID(kb),
                filename="guard.txt",
                storage_path="unused",
                size=1,
                sha256=uuid4().hex * 2,
                status="chunking",
                parse_report={"generation": "new"},
            )
            db.add(guard)
            await db.flush()
            guard_id, job = guard.id, guard.job_id
        await set_stage(guard_id, uuid4(), "embedding", parse_report={"generation": "old"})
        async with get_db_context() as db:
            guard = await db.get(KnowledgeDocument, guard_id)
            assert guard.status == "chunking" and guard.parse_report == {"generation": "new"}
        await set_stage(guard_id, job, "embedding", parse_report=report)
        async with get_db_context() as db:
            guard = await db.get(KnowledgeDocument, guard_id)
            assert guard.status == "embedding" and guard.parse_report == report
            await db.delete(guard)
        print("Stale worker generation cannot replace the extraction report: PASS", flush=True)

        result = {}
        async with websockets.connect(
            "ws://localhost:38001/api/v1/ws/agent",
            subprotocols=["access_token." + a["token"], "chat"],
        ) as ws:
            await ws.send(
                json.dumps(
                    {
                        "message": "折射率灵敏度是多少？",
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
        assert "142" in result["answer"], result
        sid = result["retrieval"]["items"][0]["citation_id"]
        source = (await req("GET", f"/knowledge/citations/{sid}")).json()
        assert source["parse_report"] == report and source["quotes"] and source["page"] == 1, source
        assert (await req("GET", f"/knowledge/citations/{sid}", user=b)).status_code == 404
        # Retry is checked inside a transaction before the API dispatches a replacement job.
        async with get_db_context() as db:
            document = await KnowledgeService(db, UUID(a["id"])).retry(UUID(did))
            assert document.parse_report is None and document.status == "pending"
        retained = (await req("GET", f"/knowledge/citations/{sid}")).json()
        assert retained["state"] == "reindexed" and retained["parse_report"] == report
        r = await req("POST", f"/knowledge/documents/{did}/retry")
        assert r.status_code == 200
        assert (await ready(kb))["parse_report"] == report
        print(
            "Live PDF answer retains extraction report snapshot; reprocessing clears and rebuilds current report: PASS",
            flush=True,
        )
        a.update(
            base_id=kb, document_id=did, citation_id=sid, conversation_id=result["conversation_id"]
        )
        p = Path("/tmp/pdf-fixtures.json")
        p.write_text(json.dumps(users))
        p.chmod(0o600)
        Path("/tmp/mixed-columns.pdf").write_bytes(raw)


if __name__ == "__main__":
    asyncio.run(main())
