"""Project defaults are references, not ownership transfers."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    knowledge_base_ids: list[UUID] = Field(default_factory=list, max_length=5)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("请输入项目名称")
        return value.strip()


class ProjectResponse(ProjectWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
