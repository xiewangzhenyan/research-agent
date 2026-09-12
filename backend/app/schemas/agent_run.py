"""Strict, bounded task contracts; checkpoint identifiers never come from clients."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.knowledge import RetrievalConfig
from app.schemas.model_config import GenerationOptions


class AgentRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: UUID
    prompt: str = Field(min_length=1, max_length=1500)
    mode: Literal["standard", "knowledge_collaboration"] = "standard"
    knowledge_base_ids: list[UUID] = Field(default_factory=list, max_length=5)
    tools: list[Literal["current_datetime", "ask_user", "run_python"]] | None = Field(
        default=None, max_length=3
    )
    input_file_ids: list[UUID] = Field(default_factory=list, max_length=5)
    generation: GenerationOptions = Field(default_factory=GenerationOptions)
    retrieval_config: RetrievalConfig | None = None

    @field_validator("prompt")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("请输入任务内容")
        return value.strip()


class AgentRunResume(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str = Field(min_length=1, max_length=64)
    answers: dict[str, list[str]] = Field(min_length=1, max_length=10)

    @field_validator("answers")
    @classmethod
    def bounded_answers(cls, value):
        if any(
            len(k) > 200 or not 1 <= len(v) <= 10 or any(not a.strip() or len(a) > 2000 for a in v)
            for k, v in value.items()
        ):
            raise ValueError("请填写有效答案，每项最多 2000 字")
        return value


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request: dict
    effective_config: dict
    status: str
    attempt: int
    event_seq: int
    result: dict | None
    pending_input: dict | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AgentRunEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    seq: int
    kind: str
    data: dict
    created_at: datetime
