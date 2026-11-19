"""Scoped control commands; no user-supplied progress or tool success."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.artifact_validation import ArtifactValidation


class WorkTaskSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["new", "continue", "revise", "replace", "pause", "cancel", "complete"]
    task_id: UUID | None = None
    expected_revision: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def selection(self):
        if self.action == "new":
            if self.task_id is not None or self.expected_revision is not None:
                raise ValueError("新任务不能指定已有任务版本")
        elif self.task_id is None or self.expected_revision is None:
            raise ValueError("请指定任务及当前版本")
        return self


class WorkTaskControl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: UUID
    expected_revision: int = Field(ge=1, strict=True)
    action: Literal["pause", "cancel", "complete"]


class WorkRequirementContext(BaseModel):
    version: int
    message_id: str
    requirement: str


class WorkProgressContext(BaseModel):
    run_id: str | None
    revision: int
    status: str
    phase: str
    historical: bool


class WorkArtifactContext(BaseModel):
    id: str
    run_id: str
    revision: int
    name: str
    size: int
    sha256: str
    historical: bool
    verification: Literal["not_verified"] = "not_verified"
    validation: ArtifactValidation | None = None


class WorkContextSnapshot(BaseModel):
    """Rebuilt from authorized business records, never from a chat summary."""

    version: Literal["work-context-v1"] = "work-context-v1"
    task_id: str
    revision: int
    status: str
    current_message_id: str
    requirements: list[WorkRequirementContext]
    progress: list[WorkProgressContext] = Field(default_factory=list, max_length=10)
    artifacts: list[WorkArtifactContext] = Field(default_factory=list, max_length=10)
    previous_results: list[dict] = Field(default_factory=list, max_length=3)
