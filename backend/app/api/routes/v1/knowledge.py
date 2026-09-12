"""Authenticated knowledge API, implemented entirely in this application."""

import asyncio
import logging
from datetime import datetime
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.deps import CurrentUser, DBSession
from app.core.exceptions import BadRequestError, NotFoundError
from app.schemas.knowledge import ChunkingConfig, RetrievalConfig
from app.schemas.knowledge_entry import EntryCreate, EntryRead, EntryUpdate
from app.services.file_storage import get_file_storage
from app.services.knowledge import MAX_DOCUMENT_BYTES, KnowledgeService
from app.services.knowledge_terms import terminology_metadata

router = APIRouter(prefix="/knowledge")
logger = logging.getLogger(__name__)


class BaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v):
        if not v.strip():
            raise ValueError("名称不能为空")
        return v.strip()


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    knowledge_base_id: UUID
    filename: str
    size: int
    status: str
    error: str | None
    chunk_count: int
    created_at: datetime
    parse_report: dict | None = None
    chunking_config: ChunkingConfig | None = None
    source_kind: str = "file"
    revision: int = 1
    title: str | None = None


class SearchRequest(BaseModel):
    knowledge_base_ids: list[UUID] = Field(min_length=1, max_length=5)
    query: str = Field(min_length=1, max_length=1500)
    top_k: int | None = Field(default=None, ge=1, le=10)
    retrieval_config: RetrievalConfig | None = None
    diagnostics: bool = False
    document_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=5)


async def dispatch(document_id):
    try:
        from app.worker.tasks.knowledge import index_document

        await asyncio.to_thread(index_document.delay, str(document_id))
    except Exception:
        # The document row is a durable outbox. Beat will dispatch it on recovery.
        logger.warning("Index queue unavailable; document remains pending", exc_info=True)


@router.get("/bases")
async def list_bases(user: CurrentUser, db: DBSession):
    return {"items": await KnowledgeService(db, user.id).list_bases()}


@router.post("/bases", status_code=201)
async def create_base(body: BaseCreate, user: CurrentUser, db: DBSession):
    return await KnowledgeService(db, user.id).create_base(body.name, body.description)


@router.get("/bases/{base_id}/documents", response_model=list[DocumentRead])
async def documents(base_id: UUID, user: CurrentUser, db: DBSession):
    return await KnowledgeService(db, user.id).list_documents(base_id)


@router.put("/bases/{base_id}/chunking-config")
async def update_chunking_config(
    base_id: UUID, body: ChunkingConfig, user: CurrentUser, db: DBSession
):
    return await KnowledgeService(db, user.id).update_chunking_config(base_id, body)


@router.post("/bases/{base_id}/preview")
async def preview_chunks(
    base_id: UUID,
    user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
    chunk_size: int = Form(default=450, ge=256, le=500),
    chunk_overlap: int = Form(default=65, ge=0, le=128),
):
    from pydantic import ValidationError

    from app.services.knowledge_preview import issue_receipt, run_preview, validate_file

    await KnowledgeService(db, user.id).get_base(base_id)
    try:
        config = ChunkingConfig(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    except ValidationError as exc:
        raise BadRequestError(message="重叠长度必须小于片段长度的一半") from exc
    data = await file.read(MAX_DOCUMENT_BYTES + 1)
    filename = validate_file(file.filename or "document", data)
    result = await run_preview(data, filename, config)
    result["preview_token"] = issue_receipt(user.id, base_id, filename, data, config)
    return result


@router.post("/bases/{base_id}/documents", response_model=DocumentRead, status_code=201)
async def upload(
    base_id: UUID,
    user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
    preview_token: str | None = Form(default=None, max_length=4096),
):
    data = await file.read(MAX_DOCUMENT_BYTES + 1)
    doc = await KnowledgeService(db, user.id).upload(
        base_id, file.filename or "document", data, preview_token=preview_token
    )
    await db.commit()  # Commit the durable job before publishing to the queue.
    if doc.status == "pending":
        await dispatch(doc.id)
    return doc


@router.post("/bases/{base_id}/entries", response_model=DocumentRead, status_code=201)
async def create_entry(base_id: UUID, body: EntryCreate, user: CurrentUser, db: DBSession):
    from app.services.knowledge_entries import KnowledgeEntryService

    doc = await KnowledgeEntryService(db, user.id).create_entry(base_id, body)
    await db.commit()
    await dispatch(doc.id)
    return doc


@router.get("/documents/{document_id}/entry", response_model=EntryRead)
async def read_entry(document_id: UUID, user: CurrentUser, db: DBSession):
    from app.services.knowledge_entries import KnowledgeEntryService

    return await KnowledgeEntryService(db, user.id).read_entry(document_id)


@router.put("/documents/{document_id}/entry", response_model=DocumentRead)
async def update_entry(document_id: UUID, body: EntryUpdate, user: CurrentUser, db: DBSession):
    from app.services.knowledge_entries import KnowledgeEntryService

    doc = await KnowledgeEntryService(db, user.id).update_entry(document_id, body)
    await db.commit()
    if doc.status == "pending":
        await dispatch(doc.id)
    return doc


@router.post("/documents/{document_id}/retry", response_model=DocumentRead)
async def retry(document_id: UUID, user: CurrentUser, db: DBSession):
    doc = await KnowledgeService(db, user.id).retry(document_id)
    await db.commit()
    if doc.status == "pending":
        await dispatch(doc.id)
    return doc


@router.delete("/documents/{document_id}", status_code=204)
async def remove_document(document_id: UUID, user: CurrentUser, db: DBSession):
    path = await KnowledgeService(db, user.id).remove_document(document_id)
    await db.commit()
    if path:
        await get_file_storage().delete(path)


@router.delete("/bases/{base_id}", status_code=204)
async def remove_base(base_id: UUID, user: CurrentUser, db: DBSession):
    paths = await KnowledgeService(db, user.id).remove_base(base_id)
    await db.commit()
    for path in paths:
        if path:
            await get_file_storage().delete(path)


@router.get("/documents/{document_id}/download")
async def download(document_id: UUID, user: CurrentUser, db: DBSession):
    doc = await KnowledgeService(db, user.id).get_document(document_id)
    if doc.source_kind != "file":
        from app.services.knowledge_entries import source_text

        return Response(
            source_text(doc.source_data),
            media_type="text/plain",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(doc.filename, safe='')}"
            },
        )
    path = get_file_storage().get_full_path(doc.storage_path)
    if not path:
        raise NotFoundError(message="原文文件不存在")
    return FileResponse(path, filename=doc.filename, content_disposition_type="attachment")


@router.get("/documents/{document_id}/chunks")
async def chunks(document_id: UUID, user: CurrentUser, db: DBSession):
    from sqlalchemy import select

    from app.db.models.knowledge import KnowledgeChunk

    await KnowledgeService(db, user.id).get_document(document_id)
    rows = await db.scalars(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == document_id)
        .order_by(KnowledgeChunk.position)
        .limit(1200)
    )
    return {
        "items": [
            {
                "id": str(c.id),
                "position": c.position,
                "page": c.page,
                "content": c.content,
                "location": c.location,
            }
            for c in rows
        ]
    }


@router.get("/retrieval-config", response_model=RetrievalConfig)
async def get_retrieval_config(user: CurrentUser, db: DBSession):
    return await KnowledgeService(db, user.id).get_retrieval_config()


@router.put("/retrieval-config", response_model=RetrievalConfig)
async def update_retrieval_config(body: RetrievalConfig, user: CurrentUser, db: DBSession):
    return await KnowledgeService(db, user.id).update_retrieval_config(body)


@router.post("/search")
async def search(body: SearchRequest, user: CurrentUser, db: DBSession):
    if not body.query.strip():
        raise BadRequestError(message="请输入检索内容")
    diagnostics = {} if body.diagnostics else None
    items = await KnowledgeService(db, user.id).search(
        body.knowledge_base_ids,
        body.query,
        body.top_k,
        document_ids=body.document_ids,
        config=body.retrieval_config,
        diagnostics=diagnostics,
    )
    response = {"items": items, "terminology": terminology_metadata(body.query)}
    if diagnostics is not None:
        response["diagnostics"] = diagnostics
    return response


@router.get("/citations/{citation_id}")
async def citation(citation_id: UUID, user: CurrentUser, db: DBSession):
    from app.services.knowledge_citations import read_citation

    return await read_citation(db, user.id, citation_id)


@router.get("/documents/{document_id}/preview")
async def preview(document_id: UUID, user: CurrentUser, db: DBSession):
    doc = await KnowledgeService(db, user.id).get_document(document_id)
    if not doc.filename.lower().endswith(".pdf"):
        raise BadRequestError(message="此格式请下载原文查看")
    path = get_file_storage().get_full_path(doc.storage_path)
    if not path:
        raise NotFoundError(message="原文文件不存在")
    return FileResponse(
        path, media_type="application/pdf", filename=doc.filename, content_disposition_type="inline"
    )


@router.get("/citations/{citation_id}/context")
async def citation_context(citation_id: UUID, user: CurrentUser, db: DBSession):
    from app.services.knowledge_citations import read_citation_context

    return await read_citation_context(db, user.id, citation_id)
