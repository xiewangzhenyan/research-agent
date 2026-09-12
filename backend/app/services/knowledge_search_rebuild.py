"""Re-embed unknown historical vectors without changing the live source generation."""

import asyncio
import hashlib

from sqlalchemy import delete, select

from app.core.exceptions import AlreadyExistsError, BadRequestError
from app.db.models.knowledge import KnowledgeChunk
from app.db.models.knowledge_search import KnowledgeSearchChunk
from app.db.session import get_worker_db_context
from app.repositories.knowledge_search import KnowledgeSearchRepository
from app.services.knowledge import KnowledgeService
from app.services.knowledge_index import MODEL, embed
from app.services.knowledge_search_index import lexical_data, model_fingerprint, tokenizer_version


async def rebuild_document(user_id, document_id):
    async with get_worker_db_context() as db:
        doc = await KnowledgeService(db, user_id).get_document(document_id)
        if doc.status != "ready" or doc.embedding_model != MODEL:
            raise BadRequestError(message="资料尚未就绪，请先完成原生处理")
        generation = doc.job_id
        chunks = list(
            await db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == document_id)
                .order_by(KnowledgeChunk.position)
            )
        )
        original = [(c.id, c.content) for c in chunks]
    vectors = await asyncio.to_thread(embed, [content for _, content in original])
    fingerprint = await asyncio.to_thread(model_fingerprint)
    terms = await asyncio.to_thread(lambda: [lexical_data(content) for _, content in original])
    async with get_worker_db_context() as db:
        doc = await KnowledgeService(db, user_id).get_document(document_id)
        current = list(
            await db.execute(
                select(KnowledgeChunk.id, KnowledgeChunk.content)
                .where(KnowledgeChunk.document_id == document_id)
                .order_by(KnowledgeChunk.position)
            )
        )
        if doc.job_id != generation or doc.status != "ready" or current != original:
            raise AlreadyExistsError(message="重建期间资料已更新，未发布新索引，请重新执行")
        await db.execute(
            delete(KnowledgeSearchChunk).where(
                KnowledgeSearchChunk.chunk_id.in_([cid for cid, _ in original])
            )
        )
        await KnowledgeSearchRepository(db, user_id).add(
            [
                KnowledgeSearchChunk(
                    chunk_id=cid,
                    generation_id=generation,
                    model_fingerprint=fingerprint,
                    tokenizer_version=tokenizer_version(),
                    source_hash=hashlib.md5(content.encode(), usedforsecurity=False).hexdigest(),
                    embedding=vector,
                    **term,
                )
                for (cid, content), vector, term in zip(original, vectors, terms, strict=True)
            ]
        )
    return len(original)
