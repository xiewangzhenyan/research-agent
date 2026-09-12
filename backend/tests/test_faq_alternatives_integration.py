"""Opt-in FAQ indexing lifecycle in a disposable migrated PostgreSQL database."""

import asyncio
import os
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.db.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.db.session import get_worker_db_context
from app.schemas.knowledge_entry import FAQCreate, FAQUpdate
from app.services.knowledge_entries import KnowledgeEntryService, source_text
from app.worker.tasks.knowledge import process_document
from tests.test_database_retrieval import FINGERPRINT, corpus, search, vector

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_TASK_DB_TESTS") != "1", reason="requires disposable database"
)


async def index(document_id):
    # Real queue processing/SQL/BM25; a fixed test vector avoids external model downloads.
    with (
        patch(
            "app.worker.tasks.knowledge.embed",
            side_effect=lambda texts: [vector(1, 0)] * len(texts),
        ),
        patch("app.worker.tasks.knowledge.model_fingerprint", return_value=FINGERPRINT),
    ):
        await process_document(document_id)


def test_aliases_retrieve_one_answer_and_edit_revokes_old_index_entries():
    async def check():
        async with corpus() as (owner, other, base_id, _):
            body = FAQCreate(
                kind="faq",
                question="报销规定是什么？",
                answer="住宿每晚620元，保留发票。",
                alternative_questions=["如何使用凭证ZX614？", "酒店费用上限是什么？"],
            )
            async with get_worker_db_context() as db:
                doc = await KnowledgeEntryService(db, owner).create_entry(base_id, body)
                doc_id = doc.id
                assert doc.status == "pending"
            async with get_worker_db_context() as db:
                with pytest.raises(NotFoundError):
                    await KnowledgeEntryService(db, other).read_entry(doc_id)
            await index(doc_id)
            async with get_worker_db_context() as db:
                doc = await db.get(KnowledgeDocument, doc_id)
                assert doc.status == "ready", doc.error
                assert doc.chunk_count == 3
                first_generation = doc.job_id
                entry = await KnowledgeEntryService(db, owner).read_entry(doc_id)
                assert "相似问法：如何使用凭证ZX614？" in source_text(entry["entry"])
            for mode in ("keyword", "semantic", "hybrid"):
                hits, stats = await search(
                    owner, [base_id], "ZX614", mode=mode, context_enabled=True
                )
                assert len(hits) == 1
                assert hits[0]["document_id"] == str(doc_id)
                assert hits[0]["location"]["section"] == body.question
                assert "620元" in hits[0]["content"]
                assert stats["overlap_removed"] == (0 if mode == "keyword" else 2)
            with pytest.raises(NotFoundError):
                await search(other, [base_id], "ZX614", mode="keyword")
            update = FAQUpdate(
                kind="faq",
                question=body.question,
                answer=body.answer,
                alternative_questions=["凭证ZY728如何使用？"],
                revision=1,
            )
            async with get_worker_db_context() as db:
                with pytest.raises(NotFoundError):
                    await KnowledgeEntryService(db, other).update_entry(doc_id, update)
                updated = await KnowledgeEntryService(db, owner).update_entry(doc_id, update)
                assert updated.status == "pending" and updated.revision == 2
                assert updated.job_id != first_generation
                count = await db.scalar(
                    select(func.count())
                    .select_from(KnowledgeChunk)
                    .where(
                        KnowledgeChunk.document_id == doc_id,
                    )
                )
                assert count == 0
            async with get_worker_db_context() as db:
                with pytest.raises(AlreadyExistsError):
                    await KnowledgeEntryService(db, owner).update_entry(doc_id, update)
            await index(doc_id)
            old_hits, _ = await search(owner, [base_id], "ZX614", mode="keyword")
            new_hits, _ = await search(owner, [base_id], "ZY728", mode="keyword")
            assert old_hits == []
            assert len(new_hits) == 1 and "ZY728" in new_hits[0]["content"]

    asyncio.run(check())
