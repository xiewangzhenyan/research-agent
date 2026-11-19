"""Bounded child-role results; validation status is assigned by application code."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    document_id: str
    index: int = Field(ge=1, le=10)
    revision: int | None = None
    file_version: str | None = None
    quotes: list[str] = Field(max_length=40)


class RoleHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["role-handoff-v1"] = "role-handoff-v1"
    role: Literal["researcher", "writer", "critic"]
    validation: Literal["source_quotes_checked", "no_support", "review_approved", "review_rejected"]
    summary: str = Field(max_length=12000)
    evidence: list[EvidenceReference] = Field(default_factory=list, max_length=10)
    artifact_ids: list[str] = Field(default_factory=list, max_length=10)
    issues: list[str] = Field(default_factory=list, max_length=5)
