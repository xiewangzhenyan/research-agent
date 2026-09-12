"""Durable native indexing with atomic claims and generation guards."""

import asyncio
import hashlib
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update

from app.db.models.knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from app.db.models.knowledge_search import KnowledgeSearchChunk
from app.db.session import get_worker_db_context
from app.repositories.knowledge_search import KnowledgeSearchRepository
from app.schemas.knowledge import ChunkingConfig
from app.services.file_storage import get_file_storage
from app.services.knowledge_index import MODEL, embed, parse_with_report, split_blocks
from app.services.knowledge_search_index import lexical_data, model_fingerprint, tokenizer_version
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


async def set_stage(document_id, job_id, stage, **values):
    async with get_worker_db_context() as db:
        await db.execute(
            update(KnowledgeDocument)
            .where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.job_id == job_id,
                KnowledgeDocument.status.in_(["parsing", "chunking", "embedding"]),
            )
            .values(status=stage, **values)
        )


@celery_app.task(name="knowledge.index", soft_time_limit=240, time_limit=270)
def index_document(document_id: str):
    asyncio.run(process_document(UUID(document_id)))


async def process_document(document_id):
    job_id = None
    try:
        async with get_worker_db_context() as db:
            doc = await db.scalar(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id, KnowledgeDocument.status == "pending")
                .with_for_update(skip_locked=True)
            )
            if not doc:
                return
            doc.status, doc.processing_started_at = "parsing", datetime.now(UTC)
            doc.parse_report = None
            doc.chunking_config = None
            job_id, path, filename, base_id = (
                doc.job_id,
                doc.storage_path,
                doc.filename,
                doc.knowledge_base_id,
            )
            source_data = doc.source_data if doc.source_kind != "file" else None
            config = ChunkingConfig.model_validate(
                doc.requested_chunking_config
                or await db.scalar(
                    select(KnowledgeBase.chunking_config).where(KnowledgeBase.id == base_id)
                )
            )
        if source_data is not None:
            from app.services.knowledge_entries import entry_chunks

            await set_stage(document_id, job_id, "chunking")
            chunks = await asyncio.to_thread(entry_chunks, source_data, config)
        else:
            raw = await get_file_storage().load(path)
            pages, report = await asyncio.to_thread(parse_with_report, raw, filename)
            await set_stage(document_id, job_id, "chunking", parse_report=report)
            chunks = await asyncio.to_thread(
                split_blocks, pages, size=config.chunk_size, overlap=config.chunk_overlap
            )
        if not chunks:
            raise ValueError("无法提取有效内容，请检查文件或先完成 OCR。")
        await set_stage(document_id, job_id, "embedding")
        vectors = await asyncio.to_thread(embed, [c["content"] for c in chunks])
        fingerprint = await asyncio.to_thread(model_fingerprint)
        lexical = await asyncio.to_thread(lambda: [lexical_data(c["content"]) for c in chunks])
        async with get_worker_db_context() as db:
            base = await db.scalar(
                select(KnowledgeBase).where(KnowledgeBase.id == base_id).with_for_update()
            )
            if not base:
                return
            doc = await db.scalar(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id)
                .with_for_update()
            )
            if not doc or doc.job_id != job_id or doc.status != "embedding":
                return
            used = await db.scalar(
                select(func.coalesce(func.sum(KnowledgeDocument.chunk_count), 0)).where(
                    KnowledgeDocument.knowledge_base_id == base_id,
                    KnowledgeDocument.id != document_id,
                )
            )
            if used + len(chunks) > 2400:
                raise ValueError("知识库超过 2400 个片段，请删除部分文档或新建知识库。")
            await db.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
            )
            records = [
                KnowledgeChunk(document_id=document_id, **c, embedding=v)
                for c, v in zip(chunks, vectors, strict=True)
            ]
            db.add_all(records)
            await db.flush()
            await KnowledgeSearchRepository(db, base.user_id).add(
                [
                    KnowledgeSearchChunk(
                        chunk_id=c.id,
                        generation_id=job_id,
                        model_fingerprint=fingerprint,
                        tokenizer_version=tokenizer_version(),
                        source_hash=hashlib.md5(
                            c.content.encode(), usedforsecurity=False
                        ).hexdigest(),
                        embedding=c.embedding,
                        **terms,
                    )
                    for c, terms in zip(records, lexical, strict=True)
                ]
            )
            doc.status, doc.error, doc.chunk_count, doc.embedding_model = (
                "ready",
                None,
                len(chunks),
                MODEL,
            )
            doc.chunking_config = config.model_dump()
    except Exception as exc:
        logger.exception("Knowledge indexing failed for %s", document_id)
        error = (
            str(exc)[:300]
            if isinstance(exc, (ValueError, UnicodeDecodeError))
            else "文档处理失败，请检查文件后重试；若持续失败请联系管理员。"
        )
        async with get_worker_db_context() as db:
            await db.execute(
                update(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id, KnowledgeDocument.job_id == job_id)
                .values(status="failed", error=error, chunk_count=0)
            )


@celery_app.task(name="knowledge.dispatch")
def dispatch_pending():
    async def collect():
        async with get_worker_db_context() as db:
            stale = (
                await db.scalars(
                    select(KnowledgeDocument)
                    .where(
                        KnowledgeDocument.status.in_(
                            ["processing", "parsing", "chunking", "embedding"]
                        ),
                        KnowledgeDocument.processing_started_at
                        < datetime.now(UTC) - timedelta(minutes=6),
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for doc in stale:
                doc.status, doc.error = "failed", "任务中断或超时，请点击重试。"
                doc.job_id = uuid4()
            return [
                str(x)
                for x in await db.scalars(
                    select(KnowledgeDocument.id)
                    .where(KnowledgeDocument.status == "pending")
                    .limit(20)
                )
            ]

    for document_id in asyncio.run(collect()):
        index_document.delay(document_id)
