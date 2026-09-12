"""Atomic source edits reuse the durable native document indexing queue."""

import hashlib
import json
from uuid import uuid4

from sqlalchemy import delete, func, select

from app.core.exceptions import AlreadyExistsError, BadRequestError, NotFoundError
from app.db.models.knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from app.schemas.knowledge_entry import FAQCreate, ManualCreate
from app.services.knowledge import KnowledgeService
from app.services.knowledge_index import split_blocks, split_document


def source_text(entry):
    if entry["kind"] == "manual":
        return f"# {entry['title']}\n\n{entry['content']}\n"
    return f"问题：{entry['question']}\n答案：{entry['answer']}\n"


def entry_chunks(entry, config):
    if entry["kind"] == "manual":
        return split_blocks(
            [{"page": None, "text": source_text(entry), "location": {"kind": "manual"}}],
            size=config.chunk_size,
            overlap=config.chunk_overlap,
        )
    # Keep the question with every answer segment, within the existing encoder bound.
    prefix = f"问题：{entry['question']}\n答案："
    budget = config.chunk_size - len(prefix)
    parts = split_document(
        [(None, entry["answer"])], size=budget, overlap=min(config.chunk_overlap, budget // 3)
    )
    return [
        part
        | {
            "content": prefix + part["content"],
            "location": {"kind": "faq", "section": entry["question"]},
        }
        for part in parts
    ]


def content_values(body):
    data = body.model_dump(exclude={"revision"})
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True).encode()
    title = data.get("title") or data["question"]
    return data, title + ".md", hashlib.sha256(raw).hexdigest(), len(source_text(data).encode())


class KnowledgeEntryService(KnowledgeService):
    async def read_entry(self, document_id):
        doc = await self.get_document(document_id)
        if doc.source_kind == "file":
            raise BadRequestError(message="上传文件不支持在线编辑，请下载后修改并重新上传")
        return {"document_id": doc.id, "revision": doc.revision, "entry": doc.source_data}

    async def create_entry(self, base_id, body: ManualCreate | FAQCreate):
        await self.get_base(base_id, lock=True)
        data, filename, digest, size = content_values(body)
        await self.check_duplicate(base_id, digest)
        count = await self.db.scalar(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.knowledge_base_id == base_id)
        )
        if count >= 100:
            raise BadRequestError(message="每个知识库最多 100 条资料")
        doc = KnowledgeDocument(
            knowledge_base_id=base_id,
            filename=filename,
            storage_path="",
            size=size,
            sha256=digest,
            status="pending",
            source_kind=data["kind"],
            source_data=data,
        )
        self.db.add(doc)
        await self.db.flush()
        return doc

    async def check_duplicate(self, base_id, digest, exclude=None):
        stmt = select(KnowledgeDocument.id).where(
            KnowledgeDocument.knowledge_base_id == base_id, KnowledgeDocument.sha256 == digest
        )
        if exclude:
            stmt = stmt.where(KnowledgeDocument.id != exclude)
        if await self.db.scalar(stmt):
            raise AlreadyExistsError(message="相同内容已在此知识库中，请查看已有资料")

    async def update_entry(self, document_id, body):
        # Lock ordering matches publication/deletion: base, then document.
        base_id = await self.db.scalar(
            select(KnowledgeDocument.knowledge_base_id)
            .join(KnowledgeBase)
            .where(KnowledgeDocument.id == document_id, KnowledgeBase.user_id == self.user_id)
        )
        if not base_id:
            raise NotFoundError(message="资料不存在或无权访问")
        await self.get_base(base_id, lock=True)
        doc = await self.get_document(document_id)
        if doc.source_kind == "file" or doc.source_kind != body.kind:
            raise BadRequestError(message="不能更改资料类型或在线编辑上传文件")
        if doc.revision != body.revision:
            raise AlreadyExistsError(
                message="内容已在其他页面修改。请先复制保留当前修改，再重新加载最新版本",
                code="REVISION_CONFLICT",
            )
        data, filename, digest, size = content_values(body)
        if digest == doc.sha256:
            return doc
        await self.check_duplicate(base_id, digest, exclude=doc.id)
        doc.source_data, doc.filename, doc.sha256, doc.size = data, filename, digest, size
        doc.revision += 1
        doc.job_id = uuid4()
        doc.status, doc.error, doc.chunk_count = "pending", None, 0
        doc.parse_report, doc.chunking_config, doc.requested_chunking_config = None, None, None
        doc.processing_started_at = None
        await self.db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id))
        await self.db.flush()
        return doc
