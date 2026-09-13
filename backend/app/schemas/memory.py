from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=1200)
    kind: Literal["preference", "decision", "constraint", "note"] = "note"
    pinned: bool = False
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


class MemoryPreferenceWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    revision: int = Field(ge=0)


class MemoryPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=2000)


class MemoryUsageItem(BaseModel):
    id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    revision: int = Field(ge=1)


class MemoryUsage(BaseModel):
    status: Literal["used", "disabled", "no_match", "strict_knowledge"]
    items: list[MemoryUsageItem] = Field(max_length=6)
    omitted: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0, le=1600)
