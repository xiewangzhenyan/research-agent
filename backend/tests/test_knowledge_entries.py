"""Authored source bounds, question-preserving chunks and revision conflict guards."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from app.core.exceptions import AlreadyExistsError, BadRequestError
from app.schemas.knowledge import ChunkingConfig
from app.schemas.knowledge_entry import EntryCreate, FAQCreate, FAQUpdate, ManualCreate
from app.services.knowledge_entries import (
    KnowledgeEntryService,
    content_values,
    entry_chunks,
    source_text,
)


@pytest.mark.parametrize(
    "entry",
    [
        {"kind": "manual", "title": " ", "content": "body"},
        {"kind": "faq", "question": "q", "answer": " "},
        {"kind": "faq", "question": "q" * 151, "answer": "a"},
        {"kind": "manual", "title": "t", "content": "x" * 20001},
        {"kind": "faq", "question": "q", "answer": "a" * 10001},
        {"kind": "faq", "question": "q", "answer": "\x00"},
        {"kind": "file", "title": "t", "content": "body"},
        {"kind": "faq", "question": "q", "answer": "a", "id": "foreign"},
    ],
)
def test_invalid_authored_input_rejected(entry):
    with pytest.raises(ValidationError):
        TypeAdapter(EntryCreate).validate_python(entry)


@pytest.mark.parametrize("size,overlap", [(256, 127), (450, 65), (500, 0)])
def test_long_faq_answer_keeps_question_and_fits_encoder_without_losing_tail(size, overlap):
    entry = FAQCreate(
        kind="faq", question="问题" * 75, answer="ABCDEFGHIJ" * 250 + "最终条件620元"
    ).model_dump()
    chunks = entry_chunks(entry, ChunkingConfig(chunk_size=size, chunk_overlap=overlap))
    assert len(chunks) > 1
    assert all(len(c["content"]) <= size and c["page"] is None for c in chunks)
    assert all(c["content"].startswith("问题：" + entry["question"] + "\n答案：") for c in chunks)  # noqa: RUF001 - source punctuation
    assert "最终条件620元" in chunks[-1]["content"]
    assert [c["position"] for c in chunks] == list(range(len(chunks)))
    assert all(c["location"]["kind"] == "faq" for c in chunks)


def test_manual_source_and_digest_are_deterministic_and_type_specific():
    body = ManualCreate(kind="manual", title="  标题 ", content="正文")
    data, filename, digest, size = content_values(body)
    assert data["title"] == "标题" and filename == "标题.md"
    assert size == len(source_text(data).encode()) and len(digest) == 64
    assert entry_chunks(data, ChunkingConfig())[0]["content"] == "# 标题\n\n正文"
    assert content_values(FAQCreate(kind="faq", question="标题", answer="正文"))[2] != digest


@pytest.mark.anyio
async def test_stale_revision_or_kind_never_mutates_or_deletes_existing_index():
    db = AsyncMock()
    db.scalar.return_value = uuid4()
    service = KnowledgeEntryService(db, uuid4())
    service.get_base = AsyncMock()
    doc = SimpleNamespace(source_kind="faq", revision=2)
    service.get_document = AsyncMock(return_value=doc)
    with pytest.raises(AlreadyExistsError) as caught:
        await service.update_entry(
            uuid4(), FAQUpdate(kind="faq", question="q", answer="a", revision=1)
        )
    assert caught.value.code == "REVISION_CONFLICT"
    doc.source_kind = "file"
    with pytest.raises(BadRequestError):
        await service.update_entry(
            uuid4(), FAQUpdate(kind="faq", question="q", answer="a", revision=2)
        )
    db.execute.assert_not_called()
    db.flush.assert_not_called()


@pytest.mark.anyio
async def test_identical_save_is_noop_including_revision_and_job():
    body = FAQUpdate(kind="faq", question="q", answer="a", revision=2)
    db = AsyncMock()
    db.scalar.return_value = uuid4()
    service = KnowledgeEntryService(db, uuid4())
    service.get_base = AsyncMock()
    doc = SimpleNamespace(source_kind="faq", revision=2, sha256=content_values(body)[2])
    service.get_document = AsyncMock(return_value=doc)
    assert await service.update_entry(uuid4(), body) is doc
    db.execute.assert_not_called()
    db.flush.assert_not_called()
