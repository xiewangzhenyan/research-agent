"""Conversation schemas for AI chat persistence.

This module contains Pydantic schemas for Conversation, Message, and ToolCall entities.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from app.schemas.base import BaseSchema, TimestampSchema
from app.schemas.model_config import EffectiveGenerationConfig


class ToolCallBase(BaseSchema):
    """Base tool call schema."""

    tool_call_id: str = Field(..., description="External tool call ID from AI framework")
    tool_name: str = Field(..., max_length=100, description="Name of the tool called")
    args: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class ToolCallCreate(ToolCallBase):
    """Schema for creating a tool call record."""

    started_at: datetime | None = Field(default=None, description="When the tool call started")


class ToolCallComplete(BaseSchema):
    """Schema for completing a tool call."""

    result: str = Field(..., description="Tool execution result")
    completed_at: datetime | None = Field(default=None, description="When the tool call completed")
    success: bool = Field(default=True, description="Whether the tool call succeeded")


class ToolCallRead(ToolCallBase):
    """Schema for reading a tool call (API response)."""

    id: UUID
    message_id: UUID
    result: str | None = None
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None


class ToolCallStat(BaseSchema):
    """One tool's aggregated stats over a window."""

    tool_name: str
    total_calls: int
    failed_calls: int
    avg_duration_ms: int | None = None
    last_used_at: datetime | None = None


class ToolCallStatList(BaseSchema):
    items: list[ToolCallStat]
    days: int


class MessageBase(BaseSchema):
    """Base message schema."""

    role: Literal["user", "assistant", "system"] = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    thinking: str | None = Field(default=None, description="Reasoning trace (assistant turns)")


class MessageCreate(MessageBase):
    """Schema for creating a message."""

    model_name: str | None = Field(default=None, max_length=100, description="AI model used")
    tokens_used: int | None = Field(default=None, ge=0, description="Token count")
    effective_config: EffectiveGenerationConfig | None = None


class UserMessageCreate(BaseSchema):
    """Client-submitted text; assistant/system messages are server-generated."""

    model_config = ConfigDict(extra="forbid")
    role: Literal["user"] = "user"
    content: str = Field(min_length=1, max_length=30000)


class MessageFileRead(BaseSchema):
    """Schema for file attached to a message."""

    id: UUID
    filename: str
    mime_type: str
    file_type: str


class MessageRead(MessageBase, TimestampSchema):
    """Schema for reading a message (API response)."""

    id: UUID
    conversation_id: UUID
    model_name: str | None = None
    tokens_used: int | None = None
    effective_config: EffectiveGenerationConfig | None = None
    tool_calls: list[ToolCallRead] = Field(default_factory=list)
    files: list[MessageFileRead] = Field(default_factory=list)
    user_rating: int | None = Field(
        default=None,
        description="Current user's rating (1 or -1)",
    )
    rating_count: dict[str, int] | None = Field(
        default=None,
        description="Aggregate counts {likes: N, dislikes: N}",
    )


class MessageReadSimple(MessageBase, TimestampSchema):
    """Simplified message schema without tool calls."""

    id: UUID
    conversation_id: UUID
    model_name: str | None = None
    tokens_used: int | None = None


class ConversationBase(BaseSchema):
    """Base conversation schema."""

    title: str | None = Field(default=None, max_length=255, description="Conversation title")


class ConversationCreate(ConversationBase):
    """Schema for creating a conversation."""

    user_id: UUID | None = Field(default=None, description="Owner user ID")


class ConversationUpdate(BaseSchema):
    """Schema for updating a conversation."""

    title: str | None = Field(default=None, max_length=255)
    active_knowledge_base_ids: list[UUID] = Field(default_factory=list, max_length=5)
    active_knowledge_document_ids: list[UUID] | None = Field(
        default=None, min_length=1, max_length=5
    )
    knowledge_strict: bool = True
    is_archived: bool | None = None
    is_demo: bool | None = None


class ConversationRead(ConversationBase, TimestampSchema):
    """Schema for reading a conversation (API response)."""

    id: UUID
    user_id: UUID | None = None
    active_knowledge_base_ids: list[UUID] = Field(default_factory=list)
    active_knowledge_document_ids: list[UUID] | None = Field(
        default=None, min_length=1, max_length=5
    )
    knowledge_strict: bool = True
    is_archived: bool = False
    is_demo: bool = False


class ConversationReadWithMessages(ConversationRead):
    """Conversation with all messages."""

    messages: list[MessageRead] = Field(default_factory=list)


class ConversationList(BaseSchema):
    """Schema for listing conversations."""

    items: list[ConversationRead]
    total: int


class MessageList(BaseSchema):
    """Schema for listing messages."""

    items: list[MessageRead]
    total: int


class ConversationWithLatestMessage(ConversationRead):
    """Conversation with its latest message for list views."""

    latest_message: MessageReadSimple | None = None
    message_count: int = 0


class ConversationAdminList(BaseSchema):
    """Schema for admin conversation list with message counts."""

    items: list[ConversationWithLatestMessage]
    total: int


class ConversationExport(BaseSchema):
    conversations: list[Any]
    total: int


class DemoConversationSummary(BaseSchema):
    """Lightweight card for the public demo gallery."""

    id: UUID
    title: str | None = None
    message_count: int = 0
    preview: str | None = Field(
        default=None, description="First user prompt, truncated to 200 chars"
    )
    created_at: datetime
    updated_at: datetime | None = None


class DemoConversationList(BaseSchema):
    """Paginated list of public demo conversations."""

    items: list[DemoConversationSummary]
    total: int
