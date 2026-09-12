"""Authored source bounds, question-preserving chunks and revision conflict guards."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from app.core.exceptions import AlreadyExistsError, BadRequestError, NotFoundError
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
    assert all(c["content"].startswith("问题：" + entry["question"] + "\n答案：") for c in chunks)
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


@pytest.mark.parametrize("questions", [[" "], ["a\x00"], ["x" * 151], ["q"] * 6, "question"])
def test_invalid_alternatives_are_rejected(questions):
    with pytest.raises(ValidationError):
        FAQCreate(kind="faq", question="标准问题", answer="答案", alternative_questions=questions)


def test_alternatives_are_normalized_and_legacy_content_hash_is_unchanged():
    import hashlib
    import json

    legacy = {"kind": "faq", "question": "LSPR", "answer": "标准答案"}
    body = FAQCreate(**legacy, alternative_questions=[" lspr ", "如何测量？", " 如何测量？ "])
    assert body.alternative_questions == ["如何测量？"]
    assert "相似问法：如何测量？\n" in source_text(body.model_dump())
    old_hash = hashlib.sha256(
        json.dumps(legacy, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    assert content_values(FAQCreate(**legacy))[2] == old_hash
    assert content_values(body)[2] != old_hash


@pytest.mark.parametrize("size", [256, 450, 500])
def test_every_phrasing_keeps_the_complete_long_answer_and_original_citation(size):
    entry = FAQCreate(
        kind="faq",
        question="标准问题",
        answer="ABCDEFGHIJ" * 250 + "最后的限制条件",
        alternative_questions=["最长问法" * 37, "简短问法"],
    ).model_dump()
    chunks = entry_chunks(entry, ChunkingConfig(chunk_size=size))
    assert [c["position"] for c in chunks] == list(range(len(chunks)))
    assert all(len(c["content"]) <= size for c in chunks)
    assert all(c["location"]["section"] == "标准问题" for c in chunks)
    variants = [[c for c in chunks if c["location"]["question_variant"] == i] for i in range(3)]
    assert len({len(group) for group in variants}) == 1
    for group in variants:
        assert "最后的限制条件" in group[-1]["content"]
    for pieces in zip(*variants, strict=True):
        assert len({c["content"].split("\n答案：", 1)[1] for c in pieces}) == 1
        assert len({c["location"]["answer_part"] for c in pieces}) == 1


@pytest.mark.anyio
async def test_foreign_entry_update_cannot_touch_index_or_source():
    db = AsyncMock()
    db.scalar.return_value = None
    service = KnowledgeEntryService(db, uuid4())
    service.get_base = AsyncMock()
    with pytest.raises(NotFoundError):
        await service.update_entry(
            uuid4(),
            FAQUpdate(
                kind="faq",
                question="q",
                answer="a",
                alternative_questions=["alias"],
                revision=1,
            ),
        )
    service.get_base.assert_not_called()
    db.execute.assert_not_called()


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
