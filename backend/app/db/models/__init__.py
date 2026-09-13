"""Database models."""

# ruff: noqa: I001, RUF022 - Imports structured for Jinja2 template conditionals
from app.db.models.user import User
from app.db.models.conversation import Conversation, Message, ToolCall
from app.db.models.chat_file import ChatFile
from app.db.models.message_rating import MessageRating
from app.db.models.conversation_share import ConversationShare
from app.db.models.user_slash_command import UserSlashCommand

__all__ = [
    "User",
    "Conversation",
    "Message",
    "ToolCall",
    "ChatFile",
    "MessageRating",
    "ConversationShare",
    "UserSlashCommand",
    "KnowledgeBase",
    "KnowledgeDocument",
    "KnowledgeChunk",
    "KnowledgeCitation",
    "AgentRun",
    "AgentRunEvent",
    "KnowledgeSearchChunk",
    "RunArtifact",
    "Project",
    "MemoryItem",
    "MemoryPreference",
    "MemoryVersion",
    "MemoryProposal",
    "MemoryExtractionJob",
]

from app.db.models.knowledge import (
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeChunk,
    KnowledgeCitation,
)

from app.db.models.agent_run import AgentRun, AgentRunEvent

from app.db.models.knowledge_search import KnowledgeSearchChunk

from app.db.models.run_artifact import RunArtifact
from app.db.models.project import Project

from app.db.models.memory import (
    MemoryItem,
    MemoryPreference,
    MemoryVersion,
    MemoryProposal,
    MemoryExtractionJob,
)
