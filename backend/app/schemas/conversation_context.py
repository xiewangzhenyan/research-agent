from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ContextNote(BaseModel):
    topic: str = Field(min_length=1, max_length=80)
    kind: Literal["goal", "constraint", "decision", "progress", "question"]
    source: int = Field(ge=0, le=7)
    summary: str = Field(min_length=1, max_length=500)
    quote: str = Field(min_length=4, max_length=1000)


class ContextSummary(BaseModel):
    notes: list[ContextNote] = Field(default_factory=list, max_length=12)


class ContextReference(BaseModel):
    message_id: UUID
    via: Literal["summary", "excerpt", "recent"]
    content_hash: str = Field(min_length=64, max_length=64)
    offset: int = Field(ge=0)
    length: int = Field(ge=1, le=1400)


class ContextUsage(BaseModel):
    policy: str
    recent_messages: int = Field(ge=0, le=12)
    references: list[ContextReference] = Field(default_factory=list, max_length=6)
    retrieval: Literal["recent", "keyword", "hybrid", "fallback"]
    summary_blocks: int = Field(ge=0)
    estimated_input_tokens: int = Field(ge=0)
    input_budget: int = Field(ge=0)
    output_reserved: int = Field(ge=0)
    omitted: bool = False
