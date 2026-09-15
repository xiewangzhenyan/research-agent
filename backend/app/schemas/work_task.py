"""Scoped control commands; no user-supplied progress or tool success."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
