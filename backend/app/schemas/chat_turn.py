"""A normal chat message is an acknowledged, durable server-side turn."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.model_config import GenerationOptions


class ChatTurnCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: UUID
    conversation_id: UUID | None = None
    message: str = Field(default="", max_length=30000)
    file_ids: list[UUID] = Field(default_factory=list, max_length=10)
    knowledge_base_ids: list[UUID] | None = Field(default=None, max_length=5)
    knowledge_document_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=5)
    knowledge_strict: bool | None = None
    python_enabled: bool = False
    generation: GenerationOptions = Field(default_factory=GenerationOptions)

    @model_validator(mode="after")
    def has_content(self):
        if not self.message.strip() and not self.file_ids:
            raise ValueError("请输入消息或添加附件")
        return self
