from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=1200)
    kind: Literal["preference", "decision", "constraint", "note"] = "note"
    pinned: bool = False
    expires_on: date | None = None
    source_message_id: UUID | None = None

    @field_validator("title", "content")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("标题和内容不能为空")
        return value.strip()


class MemoryUpdate(MemoryCreate):
    revision: int = Field(ge=1)


class MemoryResponse(MemoryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID | None
    revision: int
    created_at: datetime
    updated_at: datetime | None
    archived_at: datetime | None = None
    state: Literal["active", "expired", "archived"] = "active"
    index_status: Literal["pending", "ready", "failed"] = "pending"
    origin: Literal["manual", "automatic"] = "manual"
    source_quote: str | None = None


class MemoryPreferenceWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    auto_extract: bool | None = None
    semantic_recall: bool | None = None
    extraction_model: str | None = Field(default=None, max_length=100)
    revision: int = Field(ge=0)


class MemoryPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=2000)


class MemoryUsageItem(BaseModel):
    id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    revision: int = Field(ge=1)


class MemoryUsage(BaseModel):
    retrieval_mode: Literal["hybrid", "keyword"] = "keyword"
    semantic_status: str | None = None
    status: Literal["used", "disabled", "no_match", "strict_knowledge"]
    items: list[MemoryUsageItem] = Field(max_length=6)
    omitted: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0, le=1600)


class MemoryRevisionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)


class MemoryProposalAccept(MemoryCreate):
    revision: int = Field(ge=1)


class ExtractedMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=1200)
    kind: Literal["preference", "decision", "constraint", "note"]
    action: Literal["add", "update"]
    target: int | None = Field(default=None, ge=0, le=9)
    reason: str = Field(min_length=1, max_length=500)
    quote: str = Field(min_length=4, max_length=1500)
    expires_on: date | None = None
    expiry_quote: str | None = Field(default=None, max_length=300)


class ExtractionResult(BaseModel):
    memories: list[ExtractedMemory] = Field(default_factory=list, max_length=5)
