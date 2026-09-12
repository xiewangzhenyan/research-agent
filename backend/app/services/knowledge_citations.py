"""Citation lifecycle and permissions, separate from untrusted tool output."""

import json
from uuid import UUID

from sqlalchemy import select

from app.core.exceptions import NotFoundError
from app.db.models.conversation import Conversation, Message, ToolCall
from app.db.models.knowledge import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeCitation,
    KnowledgeDocument,
)


async def persist_citations(db, conversation_id, message_id, tool_calls):
    owner = await db.scalar(select(Conversation.user_id).where(Conversation.id == conversation_id))
    for tc in tool_calls:
        if tc.get("tool_name") != "search_knowledge_base" or not tc.get("result"):
            continue
        payload = json.loads(tc["result"])
        # Lock documents in stable order; deletion must serialize with saving snapshots.
        ids = sorted(
            {UUID(s["document_id"]) for s in payload.get("items", []) if s.get("citation_id")}
        )
        docs = (
            {
                str(d.id): d
                for d in await db.scalars(
                    select(KnowledgeDocument)
                    .join(KnowledgeBase)
                    .where(KnowledgeDocument.id.in_(ids), KnowledgeBase.user_id == owner)
                    .order_by(KnowledgeDocument.id)
                    .with_for_update(of=KnowledgeDocument)
                )
            }
            if ids
            else {}
        )
        for source in payload.get("items", []):
            if not source.get("citation_id"):
                continue
            doc = docs.get(source["document_id"])
            snapshot = dict(source)
            if not doc:
                snapshot = {
                    "index": source["index"],
                    "title": "原文已删除",
                    "content": "",
                    "state": "deleted",
                }
            db.add(
                KnowledgeCitation(
                    id=UUID(source["citation_id"]),
                    user_id=owner,
                    message_id=message_id,
                    document_id=doc.id if doc else None,
                    source=snapshot,
                )
            )
            # Save content only in the permission-checked citation store. Historical tool results are pointers.
            source["content"] = ""
            source.pop("url", None)
            source.pop("quotes", None)
        tc["result"] = json.dumps(payload, ensure_ascii=False)
    await db.flush()


async def read_citation(db, user_id, citation_id):
    citation = await db.scalar(
        select(KnowledgeCitation).where(
            KnowledgeCitation.id == citation_id, KnowledgeCitation.user_id == user_id
        )
    )
    if not citation:
        raise NotFoundError(message="引用不存在或无权访问")
    doc = (
        await db.scalar(
            select(KnowledgeDocument)
            .join(KnowledgeBase)
            .where(KnowledgeDocument.id == citation.document_id, KnowledgeBase.user_id == user_id)
        )
        if citation.document_id
        else None
    )
    if not doc:
        return {"state": "deleted", "title": "原文已删除", "content": ""}
    source = dict(citation.source)
    source["state"] = (
        "current" if str(doc.job_id) == source.get("index_generation") else "reindexed"
    )
    source["url"] = f"/api/knowledge/documents/{doc.id}/download"
    if doc.filename.lower().endswith(".pdf"):
        source["preview_url"] = (
            f"/api/knowledge/documents/{doc.id}/preview#page={source.get('page') or 1}"
        )
    return source


async def erase_document_citations(db, user_id, document_ids):
    """Remove snapshots and legacy tool copies while retaining conversation answers."""
    ids = {str(i) for i in document_ids}
    for citation in await db.scalars(
        select(KnowledgeCitation)
        .where(
            KnowledgeCitation.user_id == user_id, KnowledgeCitation.document_id.in_(document_ids)
        )
        .with_for_update()
    ):
        citation.source = {
            "index": citation.source.get("index"),
            "title": "原文已删除",
            "content": "",
            "state": "deleted",
        }
    for tc in await db.scalars(
        select(ToolCall)
        .join(Message)
        .join(Conversation)
        .where(
            Conversation.user_id == user_id,
            ToolCall.tool_name == "search_knowledge_base",
        )
        .with_for_update(of=ToolCall)
    ):
        try:
            payload = json.loads(tc.result or "{}")
            changed = False
            for source in payload.get("items", []):
                if source.get("document_id") in ids:
                    keep = {
                        "index": source.get("index"),
                        "citation_id": source.get("citation_id"),
                        "title": "原文已删除",
                        "content": "",
                        "state": "deleted",
                    }
                    source.clear()
                    source.update(keep)
                    changed = True
            if changed:
                tc.result = json.dumps(payload, ensure_ascii=False)
        except (ValueError, TypeError, AttributeError):
            continue


async def read_citation_context(db, user_id, citation_id):
    """Show bounded neighboring passages only from the cited index generation."""
    source = await read_citation(db, user_id, citation_id)
    if source["state"] != "current":
        return {"state": source["state"], "items": []}
    rows = list(
        await db.scalars(
            select(KnowledgeChunk)
            .join(KnowledgeDocument)
            .join(KnowledgeBase)
            .where(
                KnowledgeBase.user_id == user_id,
                KnowledgeDocument.id == UUID(source["document_id"]),
                KnowledgeDocument.job_id == UUID(source["index_generation"]),
                KnowledgeDocument.status == "ready",
                KnowledgeChunk.position.between(
                    max(0, source["position"] - 1), source["position"] + 1
                ),
            )
            .order_by(KnowledgeChunk.position)
        )
    )
    # A retry/deletion racing this read cannot mix new chunks into an old citation.
    if not any(str(row.id) == source["id"] for row in rows):
        return {"state": "changed", "items": []}
    return {
        "state": "current",
        "items": [
            {
                "id": str(row.id),
                "page": row.page,
                "position": row.position,
                "content": row.content,
                "location": row.location,
                "cited": str(row.id) == source["id"],
            }
            for row in rows
        ],
    }
