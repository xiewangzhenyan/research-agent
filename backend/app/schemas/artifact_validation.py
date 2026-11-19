"""Application-assigned file checks; never model-assigned acceptance."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ArtifactValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["artifact-check-v1"] = "artifact-check-v1"
    sha256: str
    size: int = Field(ge=0, le=2 * 1024**2)
    integrity: Literal["passed"] = "passed"
    structure: Literal["checked", "not_checked"]
    checks: list[str] = Field(max_length=8)
    content_validation: Literal["not_verified"] = "not_verified"
