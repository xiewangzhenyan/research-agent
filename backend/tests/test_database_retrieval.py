# ruff: noqa: SIM117 - Chinese fixtures; explicit nested mock scope
"""Real PostgreSQL/pgvector boundaries, BM25 math, index lifecycle and model provenance."""

import asyncio
import hashlib
import math
import os
from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, update

from app.core.config import settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.db.models.knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from app.db.models.knowledge_search import KnowledgeSearchChunk
from app.db.session import get_worker_db_context
from app.schemas.knowledge import RetrievalConfig
from app.services.knowledge import KnowledgeService
from app.services.knowledge_index import MODEL
from app.services.knowledge_search_index import lexical_data, tokenize, tokenizer_version
from tests.test_agent_runs_integration import users

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_TASK_DB_TESTS") != "1", reason="requires disposable database"
)
FINGERPRINT = "f" * 64


def vector(x, y):
    return [x, y] + [0.0] * 510


@asynccontextmanager
async def corpus():
    async with users() as (uid, other):
        bid, foreign = uuid4(), uuid4()
        async with get_worker_db_context() as db:
            db.add_all(
                [
                    KnowledgeBase(id=bid, user_id=uid, name="Owned"),
                    KnowledgeBase(id=foreign, user_id=other, name="Foreign"),
                ]
            )
        yield uid, other, bid, foreign


async def document(bid, texts, vectors=None):
    async with get_worker_db_context() as db:
        doc = KnowledgeDocument(
            knowledge_base_id=bid,
            filename="fixture.txt",
            storage_path="",
            size=1,
            sha256=str(uuid4()),
            status="ready",
            chunk_count=len(texts),
            embedding_model=MODEL,
            chunking_config={"chunk_overlap": 0},
        )
        db.add(doc)
        await db.flush()
        chunks = [
            KnowledgeChunk(
                document_id=doc.id,
                content=content,
                position=i,
                location={},
                embedding=vectors[i] if vectors else vector(1, 0),
            )
            for i, content in enumerate(texts)
        ]
        db.add_all(chunks)
        await db.flush()
        db.add_all(
            [
                KnowledgeSearchChunk(
                    chunk_id=c.id,
                    generation_id=doc.job_id,
                    model_fingerprint=FINGERPRINT,
                    tokenizer_version=tokenizer_version(),
                    source_hash=hashlib.md5(c.content.encode(), usedforsecurity=False).hexdigest(),
                    embedding=c.embedding,
                    **lexical_data(c.content),
                )
                for c in chunks
            ]
        )
        return doc.id, [c.id for c in chunks]


async def search(uid, bids, query, **options):
    stats = {}
    with (
        patch.object(settings, "RAG_SEARCH_BACKEND", "postgres"),
        patch("app.services.knowledge_database_search.model_fingerprint", return_value=FINGERPRINT),
        patch("app.services.knowledge_database_search.embed", return_value=[vector(1, 0)]),
    ):
        async with get_worker_db_context() as db:
            hits = await KnowledgeService(db, uid).search(
                bids, query, config=RetrievalConfig(**options), diagnostics=stats
            )
    return hits, stats


def test_exact_vector_filter_is_inside_database_scope():
    async def check():
        async with corpus() as (uid, other, bid, foreign):
            _, ids = await document(
                bid, ["target", "less similar"], [vector(0.8, 0.6), vector(0.6, 0.8)]
            )
            await document(foreign, ["foreign perfect"] * 30)
            hits, stats = await search(uid, [bid], "target", mode="semantic", result_limit=1)
            assert hits[0]["id"] == str(ids[0])
            assert hits[0]["score"] == pytest.approx(0.8, abs=1e-6)
            assert (
                stats["total_chunks"] == stats["indexed_chunks"] == stats["semantic_eligible"] == 2
            )
            assert stats["keyword_candidates"] == 0
            with pytest.raises(NotFoundError):
                await search(other, [bid], "target")

    asyncio.run(check())


def test_bm25_matches_formula_and_skips_vector_inference():
    async def check():
        async with corpus() as (uid, _, bid, foreign):
            _, ids = await document(bid, ["lease lease lease", "lease other", "other"])
            await document(foreign, ["lease"] * 25)
            with patch(
                "app.services.knowledge_database_search.embed",
                side_effect=AssertionError("No vector inference"),
            ):
                # search helper normally patches embed; explicitly run the service here.
                with (
                    patch.object(settings, "RAG_SEARCH_BACKEND", "postgres"),
                    patch(
                        "app.services.knowledge_database_search.model_fingerprint",
                        return_value=FINGERPRINT,
                    ),
                ):
                    async with get_worker_db_context() as db:
                        stats = {}
                        hits = await KnowledgeService(db, uid).search(
                            [bid],
                            "lease",
                            config=RetrievalConfig(mode="keyword"),
                            diagnostics=stats,
                        )
            expected = (
                math.log(1 + (3 - 2 + 0.5) / (2 + 0.5))
                * 3
                * 2.2
                / (3 + 1.2 * (0.25 + 0.75 * 3 / 2))
            )
            assert hits[0]["id"] == str(ids[0])
            assert hits[0]["score"] == pytest.approx(expected, abs=1e-6)
            assert (
                stats["keyword_eligible"] == 2
                and stats["semantic_candidates"] == stats["embedding_ms"] == 0
            )

    asyncio.run(check())


def test_chinese_terms_and_hybrid_weighted_fusion():
    async def check():
        async with corpus() as (uid, _, bid, _):
            _, ids = await document(
                bid, ["服务期限 ZX987654", "其他内容"], [vector(0, 1), vector(1, 0)]
            )
            hits, stats = await search(
                uid, [bid], "ZX987654", keyword_weight=2, semantic_weight=0.1
            )
            assert hits[0]["id"] == str(ids[0])
            assert hits[0]["score"] == pytest.approx(2 / 61, abs=1e-6)
            assert stats["merged_candidates"] == 2
            hits, stats = await search(uid, [bid], "服务期限", mode="keyword")
            assert hits[0]["id"] == str(ids[0])
            assert "期限" in tokenize("服务期限")
            assert stats["tokenizer"].startswith("jieba-0.42.1")

    asyncio.run(check())


@pytest.mark.parametrize("change", ["missing", "fingerprint", "generation", "content"])
def test_incomplete_or_stale_indexes_fail_closed(change):
    async def check():
        async with corpus() as (uid, _, bid, _):
            did, ids = await document(bid, ["lease"])
            async with get_worker_db_context() as db:
                if change == "missing":
                    await db.execute(
                        delete(KnowledgeSearchChunk).where(KnowledgeSearchChunk.chunk_id == ids[0])
                    )
                elif change == "fingerprint":
                    await db.execute(
                        update(KnowledgeSearchChunk)
                        .where(KnowledgeSearchChunk.chunk_id == ids[0])
                        .values(model_fingerprint="x" * 64)
                    )
                elif change == "generation":
                    await db.execute(
                        update(KnowledgeDocument)
                        .where(KnowledgeDocument.id == did)
                        .values(job_id=uuid4())
                    )
                else:
                    await db.execute(
                        update(KnowledgeChunk)
                        .where(KnowledgeChunk.id == ids[0])
                        .values(content="new text")
                    )
                    assert await db.get(KnowledgeSearchChunk, ids[0]) is None
            with pytest.raises(BadRequestError, match="索引"):
                await search(uid, [bid], "lease", mode="keyword")

    asyncio.run(check())


def test_context_neighbors_keep_source_identity_and_account_boundary():
    async def check():
        async with corpus() as (uid, _, bid, foreign):
            _, ids = await document(bid, ["before", "ZX987654 target", "after"])
            await document(foreign, ["ZX987654 private"])
            hits, stats = await search(
                uid, [bid], "ZX987654", mode="keyword", result_limit=1, context_enabled=True
            )
            assert {h["id"] for h in hits} == {str(v) for v in ids}
            assert stats["context"]["added"] == 2
            assert all(h["knowledge_base_id"] == str(bid) for h in hits)

    asyncio.run(check())


@pytest.mark.skipif(
    os.getenv("RUN_LOCAL_MODEL_TESTS") != "1", reason="requires mounted offline BGE model"
)
def test_native_ingestion_dual_writes_real_local_vectors():
    from app.services.knowledge_search_index import model_fingerprint
    from app.worker.tasks.knowledge import process_document

    async def check():
        async with corpus() as (uid, _, bid, _):
            async with get_worker_db_context() as db:
                doc = KnowledgeDocument(
                    knowledge_base_id=bid,
                    filename="manual.txt",
                    storage_path="",
                    size=1,
                    sha256=str(uuid4()),
                    status="pending",
                    source_kind="manual",
                    source_data={
                        "kind": "manual",
                        "title": "Policy",
                        "content": "标准服务期限为30天，不支持自动续期。",
                    },
                )
                db.add(doc)
                await db.flush()
                did = doc.id
            await process_document(did)
            async with get_worker_db_context() as db:
                doc = await db.get(KnowledgeDocument, did)
                assert doc.status == "ready", doc.error
                rows = (
                    (
                        await db.execute(
                            select(KnowledgeSearchChunk)
                            .join(KnowledgeChunk)
                            .where(KnowledgeChunk.document_id == did)
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(rows) == doc.chunk_count > 0
                assert rows[0].model_fingerprint == model_fingerprint()
                assert len(rows[0].embedding) == 512
                assert "服务" in rows[0].terms
            with patch.object(settings, "RAG_SEARCH_BACKEND", "postgres"):
                async with get_worker_db_context() as db:
                    hits = await KnowledgeService(db, uid).search([bid], "服务期限是多少？")
            assert hits and "30" in hits[0]["content"]

    asyncio.run(check())


def test_rebuild_regenerates_unknown_vectors_without_changing_sources():
    from app.services.knowledge_search_rebuild import rebuild_document

    async def check():
        async with corpus() as (uid, _, bid, _):
            did, ids = await document(bid, ["lease"])
            with (
                patch("app.services.knowledge_search_rebuild.embed", return_value=[vector(0, 1)]),
                patch(
                    "app.services.knowledge_search_rebuild.model_fingerprint", return_value="n" * 64
                ),
            ):
                assert await rebuild_document(uid, did) == 1
            async with get_worker_db_context() as db:
                original = await db.get(KnowledgeChunk, ids[0])
                shadow = await db.get(KnowledgeSearchChunk, ids[0])
                assert original.content == "lease" and original.embedding == vector(1, 0)
                assert list(shadow.embedding) == vector(0, 1)
                assert shadow.model_fingerprint == "n" * 64

    asyncio.run(check())


def test_rebuild_does_not_publish_after_concurrent_source_update():
    import threading

    from app.core.exceptions import AlreadyExistsError
    from app.services.knowledge_search_rebuild import rebuild_document

    async def check():
        async with corpus() as (uid, _, bid, _):
            did, ids = await document(bid, ["lease"])
            entered, release = threading.Event(), threading.Event()

            def slow_embed(texts):
                entered.set()
                assert release.wait(10)
                return [vector(0, 1)]

            with (
                patch("app.services.knowledge_search_rebuild.embed", side_effect=slow_embed),
                patch(
                    "app.services.knowledge_search_rebuild.model_fingerprint", return_value="n" * 64
                ),
            ):
                work = asyncio.create_task(rebuild_document(uid, did))
                assert await asyncio.to_thread(entered.wait, 10)
                try:
                    async with get_worker_db_context() as db:
                        await db.execute(
                            update(KnowledgeDocument)
                            .where(KnowledgeDocument.id == did)
                            .values(job_id=uuid4())
                        )
                finally:
                    release.set()
                with pytest.raises(AlreadyExistsError):
                    await work
            async with get_worker_db_context() as db:
                row = await db.get(KnowledgeSearchChunk, ids[0])
                assert row.model_fingerprint == FINGERPRINT

    asyncio.run(check())
