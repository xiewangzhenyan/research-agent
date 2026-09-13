"""Recall must preserve complete notes, obey budgets and keep evidence separate."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.memory import MemoryCreate
from app.services.memory import MemoryService
from app.services.memory_recall import (
    MAX_CHARACTERS,
    MAX_ITEMS,
    MAX_TOKENS_ESTIMATE,
    memory_context,
    select_memories,
    usage_record,
)


def note(content, *, title="项目笔记", pinned=False):
    return SimpleNamespace(
        id=uuid4(), revision=1, title=title, content=content, kind="note", pinned=pinned
    )


def test_chinese_and_english_match_unrelated_notes_excluded():
    chinese = note("超表面的测量温度固定为 25°C")
    english = note("Use PostgreSQL for storage")
    unrelated = note("崩铁的游戏攻略")
    assert select_memories("超表面测量", [chinese, english, unrelated])["items"][0]["id"] == str(
        chinese.id
    )
    assert select_memories("POSTGRESQL", [chinese, english, unrelated])["items"][0]["id"] == str(
        english.id
    )
    assert select_memories("如何煮咖啡", [chinese, english, unrelated])["items"] == []


def test_pins_and_budget_preserve_entire_notes_including_negations():
    pinned = note("不允许将测试结果当作实际测量。", pinned=True)
    long_notes = [note("实验数据" * 290 + "不得对外发布。") for _ in range(8)]
    result = select_memories("实验数据", [*long_notes, pinned])
    assert result["items"][0]["content"] == pinned.content
    assert result["omitted"] > 0
    assert result["estimated_tokens"] <= MAX_TOKENS_ESTIMATE
    assert len(memory_context(result)) <= MAX_CHARACTERS
    assert all(v["content"] in {n.content for n in [*long_notes, pinned]} for v in result["items"])
    short = [note(f"项目阶段 {i}", pinned=True) for i in range(20)]
    assert len(select_memories("继续", short)["items"]) == MAX_ITEMS


def test_usage_records_ids_versions_without_retaining_private_note_content():
    result = select_memories("继续", [note("私人测试内容", pinned=True)])
    usage = usage_record(result)
    assert usage["status"] == "used"
    assert set(usage["items"][0]) == {"id", "revision"}
    assert "私人测试内容" not in str(usage)
    assert "私人测试内容" in memory_context(result)


@pytest.mark.anyio
async def test_strict_evidence_and_disabled_memory_do_not_read_notes():
    service = MemoryService(AsyncMock(), uuid4())
    service.settings = AsyncMock(return_value={"enabled": False, "revision": 0})
    service.repo.list = AsyncMock()
    assert (await service.recall("问题", strict_knowledge=True))["status"] == "strict_knowledge"
    service.settings.assert_not_awaited()
    assert (await service.recall("问题"))["status"] == "disabled"
    service.repo.list.assert_not_awaited()


@pytest.mark.parametrize(
    "change",
    [{"content": " "}, {"content": "字" * 1201}, {"kind": "system"}, {"user_id": str(uuid4())}],
)
def test_invalid_or_forged_memory_is_rejected(change):
    with pytest.raises(ValidationError):
        MemoryCreate.model_validate({"title": "笔记", "content": "完整内容", **change})
