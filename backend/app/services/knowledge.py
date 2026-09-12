"""Native knowledge management. Every public operation is account scoped."""

import asyncio
import hashlib
from time import perf_counter
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.db.models.knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from app.schemas.knowledge import ChunkingConfig, RetrievalConfig
from app.services.file_storage import get_file_storage
from app.services.knowledge_index import MODEL, embed, rank_chunks

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv"}
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024


class KnowledgeService:
    def __init__(self, db: AsyncSession, user_id: UUID):
        self.db, self.user_id = db, user_id

    async def get_base(self, base_id: UUID, lock=False):
        stmt = select(KnowledgeBase).where(
            KnowledgeBase.id == base_id, KnowledgeBase.user_id == self.user_id
        )
        if lock:
            stmt = stmt.with_for_update()
        base = await self.db.scalar(stmt)
        if not base:
            raise NotFoundError(message="知识库不存在或无权访问")
        return base

    async def get_document(self, document_id: UUID):
        doc = await self.db.scalar(
            select(KnowledgeDocument)
            .join(KnowledgeBase)
            .where(KnowledgeDocument.id == document_id, KnowledgeBase.user_id == self.user_id)
            .with_for_update(of=KnowledgeDocument)
        )
        if not doc:
            raise NotFoundError(message="文档不存在或无权访问")
        return doc

    async def list_bases(self):
        rows = (
            await self.db.execute(
                select(
                    KnowledgeBase,
                    func.count(KnowledgeDocument.id),
                    func.coalesce(func.sum(KnowledgeDocument.chunk_count), 0),
                )
                .outerjoin(KnowledgeDocument)
                .where(KnowledgeBase.user_id == self.user_id)
                .group_by(KnowledgeBase.id)
                .order_by(KnowledgeBase.created_at.desc())
            )
        ).all()
        return [
            {
                "id": str(b.id),
                "name": b.name,
                "description": b.description,
                "document_count": n,
                "chunk_count": chunks,
                "created_at": b.created_at,
                "chunking_config": b.chunking_config,
            }
            for b, n, chunks in rows
        ]

    async def update_chunking_config(self, base_id: UUID, config: ChunkingConfig):
        base = await self.get_base(base_id, lock=True)
        base.chunking_config = config.model_dump()
        await self.db.flush()
        return {"chunking_config": base.chunking_config}

    async def create_base(self, name, description):
        # Lock the account row to serialize its per-account resource limit.
        from app.db.models.user import User

        await self.db.scalar(select(User).where(User.id == self.user_id).with_for_update())
        count = await self.db.scalar(
            select(func.count())
            .select_from(KnowledgeBase)
            .where(KnowledgeBase.user_id == self.user_id)
        )
        if count >= 20:
            raise BadRequestError(message="最多创建 20 个知识库")
        base = KnowledgeBase(user_id=self.user_id, name=name, description=description)
        self.db.add(base)
        await self.db.flush()
        return {"id": str(base.id), "name": base.name, "description": base.description}

    async def list_documents(self, base_id):
        await self.get_base(base_id)
        return (
            await self.db.scalars(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.knowledge_base_id == base_id)
                .order_by(KnowledgeDocument.created_at.desc())
            )
        ).all()

    async def upload(self, base_id, filename, data, preview_token=None):
        await self.get_base(base_id, lock=True)
        from app.services.knowledge_preview import validate_file, verify_receipt

        filename = validate_file(filename, data)
        requested = (
            verify_receipt(preview_token, self.user_id, base_id, filename, data).model_dump()
            if preview_token
            else None
        )
        digest = hashlib.sha256(data).hexdigest()
        existing = await self.db.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.knowledge_base_id == base_id, KnowledgeDocument.sha256 == digest
            )
        )
        if existing:
            if requested is not None:
                raise BadRequestError(message="该文件已在知识库中，请在文件列表查看或重新处理")
            return existing
        count = await self.db.scalar(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.knowledge_base_id == base_id)
        )
        if count >= 100:
            raise BadRequestError(message="每个知识库最多 100 份文档")
        storage = get_file_storage()
        path = await storage.save(str(self.user_id), filename, data)
        doc = KnowledgeDocument(
            knowledge_base_id=base_id,
            filename=filename,
            storage_path=path,
            size=len(data),
            sha256=digest,
            status="pending",
            requested_chunking_config=requested,
        )
        self.db.add(doc)
        try:
            await self.db.flush()
        except Exception:
            await storage.delete(path)
            raise
        return doc

    async def retry(self, document_id):
        doc = await self.get_document(document_id)
        if doc.status in {"pending", "processing", "parsing", "chunking", "embedding"}:
            return doc
        await self.db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id))
        doc.status, doc.error, doc.chunk_count, doc.job_id = "pending", None, 0, uuid4()
        doc.parse_report = None
        doc.chunking_config = None
        doc.requested_chunking_config = None
        await self.db.flush()
        return doc

    async def remove_document(self, document_id):
        doc = await self.get_document(document_id)
        from app.services.knowledge_citations import erase_document_citations

        await erase_document_citations(self.db, self.user_id, [doc.id])
        await self.db.delete(doc)
        await self.db.flush()
        return doc.storage_path

    async def remove_base(self, base_id):
        base = await self.get_base(base_id, lock=True)
        paths = list(
            await self.db.scalars(
                select(KnowledgeDocument.storage_path).where(
                    KnowledgeDocument.knowledge_base_id == base_id
                )
            )
        )
        from app.services.knowledge_citations import erase_document_citations

        document_ids = list(
            await self.db.scalars(
                select(KnowledgeDocument.id)
                .where(KnowledgeDocument.knowledge_base_id == base_id)
                .order_by(KnowledgeDocument.id)
                .with_for_update()
            )
        )
        await erase_document_citations(self.db, self.user_id, document_ids)
        await self.db.delete(base)
        await self.db.flush()
        return paths

    async def validate_scope(
        self, base_ids: list[UUID], document_ids: list[UUID] | None, *, require_ready=False
    ):
        if len(base_ids) > 5:
            raise BadRequestError(message="最多选择 5 个知识库")
        for base_id in set(base_ids):
            await self.get_base(base_id)
        if document_ids is None:
            return
        if not base_ids or not 1 <= len(document_ids) <= 5:
            raise BadRequestError(message="指定资料问答需选择知识库及 1–5 条资料")
        docs = list(
            await self.db.scalars(
                select(KnowledgeDocument)
                .join(KnowledgeBase)
                .where(
                    KnowledgeBase.user_id == self.user_id,
                    KnowledgeDocument.knowledge_base_id.in_(base_ids),
                    KnowledgeDocument.id.in_(document_ids),
                )
            )
        )
        if {doc.id for doc in docs} != set(document_ids):
            raise NotFoundError(message="选定资料已删除、不属于当前知识库或无权访问，请重新选择")
        if require_ready and any(
            doc.status != "ready" or doc.embedding_model != MODEL for doc in docs
        ):
            raise BadRequestError(message="选定资料尚未完成处理，请等待完成或重新选择")

    async def get_retrieval_config(self):
        from app.db.models.knowledge import KnowledgeRetrievalPreference

        pref = await self.db.get(KnowledgeRetrievalPreference, self.user_id)
        return RetrievalConfig.model_validate(pref.config) if pref else RetrievalConfig()

    async def update_retrieval_config(self, config: RetrievalConfig):
        from sqlalchemy.dialects.postgresql import insert

        from app.db.models.knowledge import KnowledgeRetrievalPreference

        await self.db.execute(
            insert(KnowledgeRetrievalPreference)
            .values(user_id=self.user_id, config=config.model_dump())
            .on_conflict_do_update(index_elements=["user_id"], set_={"config": config.model_dump()})
        )
        await self.db.flush()
        return config

    async def search(
        self,
        base_ids: list[UUID],
        query: str,
        top_k=None,
        *,
        document_ids: list[UUID] | None = None,
        config: RetrievalConfig | None = None,
        diagnostics: dict | None = None,
    ):
        started = perf_counter()
        diagnostics = diagnostics if diagnostics is not None else {}
        config = config or await self.get_retrieval_config()
        top_k = top_k if top_k is not None else config.result_limit
        if diagnostics is not None:
            diagnostics["config"] = config.model_dump()
            diagnostics["config"]["result_limit"] = top_k
            diagnostics["embedding_ms"] = 0
        if not base_ids or len(base_ids) > 5:
            raise BadRequestError(message="请选择 1–5 个知识库")
        await self.validate_scope(base_ids, document_ids, require_ready=True)
        if settings.RAG_SEARCH_BACKEND == "postgres":
            from app.services.knowledge_database_search import database_search

            return await database_search(
                self.db, self.user_id, base_ids, document_ids, query, config, top_k, diagnostics
            )
        diagnostics["engine"] = "legacy"
        diagnostics["tokenizer"] = "cjk-bigram-v1"
        stmt = (
            select(KnowledgeChunk, KnowledgeDocument, KnowledgeBase.name)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .join(KnowledgeBase, KnowledgeDocument.knowledge_base_id == KnowledgeBase.id)
            .where(
                KnowledgeBase.user_id == self.user_id,
                KnowledgeBase.id.in_(base_ids),
                KnowledgeDocument.status == "ready",
                KnowledgeDocument.embedding_model == MODEL,
            )
        )
        if document_ids is not None:
            stmt = stmt.where(KnowledgeDocument.id.in_(document_ids))
        rows = (
            await self.db.execute(
                stmt.order_by(KnowledgeChunk.document_id, KnowledgeChunk.position).limit(12001)
            )
        ).all()
        if len(rows) > 12000:
            raise BadRequestError(message="检索范围过大，请选择更少的知识库")
        chunks = [
            {
                "id": str(c.id),
                "document_id": str(d.id),
                "knowledge_base_id": str(d.knowledge_base_id),
                "title": d.title,
                "source_kind": d.source_kind,
                "revision": d.revision,
                "collection": name,
                "position": c.position,
                "page": c.page,
                "location": c.location,
                "parse_report": d.parse_report,
                "chunking_config": d.chunking_config,
                "file_version": d.sha256,
                "index_generation": str(d.job_id),
                "content": c.content,
                "embedding": c.embedding,
                "url": f"/api/knowledge/documents/{d.id}/download",
            }
            for c, d, name in rows
        ]
        vector = []
        needs_vector = config.mode != "keyword" and (
            config.mode != "hybrid" or config.semantic_weight > 0
        )
        if chunks and needs_vector:
            embedding_started = perf_counter()
            vector = (
                await asyncio.to_thread(embed, ["为这个句子生成表示以用于检索相关文章：" + query])
            )[0]
            if diagnostics is not None:
                diagnostics["embedding_ms"] = round((perf_counter() - embedding_started) * 1000)
        hits = await asyncio.to_thread(
            rank_chunks,
            query,
            vector,
            chunks,
            config.rerank_limit if config.rerank_enabled else top_k,
            config=config,
            diagnostics=diagnostics,
            deduplicate=not config.rerank_enabled,
        )
        from app.services.knowledge_enrichment import expand_context, rerank_candidates

        diagnostics["rerank"] = {"status": "disabled", "candidates": 0, "elapsed_ms": 0}
        if config.rerank_enabled:
            hits = await rerank_candidates(query, hits, top_k, diagnostics)
        diagnostics["context"] = {
            "enabled": False,
            "seed_count": len(hits),
            "added": 0,
            "added_chars": 0,
            "budget_skipped": 0,
            "max_sources": 10,
        }
        if config.context_enabled:
            hits = expand_context(hits, chunks, config, diagnostics)
        if diagnostics is not None:
            diagnostics["total_ms"] = round((perf_counter() - started) * 1000)
        return hits
