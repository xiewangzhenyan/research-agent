"""Versioned evaluation inputs; semantic judgments must be supplied by a reviewer."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.knowledge_answer import GroundedAnswer

MAX_RESEARCH_ATTEMPTS = 8000


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Requirement(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,80}$")
    text: str = Field(min_length=1, max_length=2000)


class EvaluationSource(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    document_id: str = Field(min_length=1, max_length=200)
    index: int = Field(ge=1, le=10)
    content: str = Field(min_length=1, max_length=20000)
    revision: int | None = Field(default=None, ge=1)
    file_version: str | None = Field(default=None, max_length=200)


class ResearchCase(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,80}$")
    split: Literal["development", "holdout"]
    question: str = Field(min_length=1, max_length=5000)
    requirements: list[Requirement] = Field(min_length=1, max_length=20)
    sources: list[EvaluationSource] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def identities(self):
        for values in (
            [r.id for r in self.requirements],
            [s.id for s in self.sources],
            [s.index for s in self.sources],
        ):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate evaluation identity")
        return self


class ResearchDataset(StrictModel):
    version: Literal["research-tasks-v1"] = "research-tasks-v1"
    origin: Literal["authored_synthetic", "curated_redacted"]
    description: str = Field(min_length=1, max_length=2000)
    cases: list[ResearchCase] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def identities(self):
        if len({c.id for c in self.cases}) != len(self.cases):
            raise ValueError("Duplicate case ID")
        return self


class EvaluationUsage(StrictModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class CollaborationOutcome(StrictModel):
    version: Literal["knowledge-collaboration-v1"]
    approved: bool = Field(strict=True)
    revisions: int = Field(ge=0, le=1, strict=True)


class ResearchTrial(StrictModel):
    case_id: str
    route: Literal["standard", "knowledge_collaboration"]
    status: Literal["completed", "error", "timeout"]
    source_ids: list[str] = Field(max_length=10)
    answer: GroundedAnswer | None = None
    model: str = Field(min_length=1, max_length=200)
    latency_ms: int | None = Field(default=None, ge=0)
    usage: EvaluationUsage | None = None
    # Optional measured cost; missing prices must not become a zero-cost success.
    cost_usd: float | None = Field(default=None, ge=0)
    error_type: str | None = Field(default=None, max_length=100)
    collaboration: CollaborationOutcome | None = None
    configuration_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def outcome(self):
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("Duplicate source ID")
        if (self.status == "completed") != (self.answer is not None):
            raise ValueError("Only completed trials have an answer")
        if self.route == "standard" and self.collaboration is not None:
            raise ValueError("Standard trials cannot carry collaboration approval")
        if (
            self.route == "knowledge_collaboration"
            and self.status == "completed"
            and self.collaboration is None
        ):
            raise ValueError(
                "Completed collaboration trials require the final publication decision"
            )
        return self


class ResearchSnapshot(StrictModel):
    version: Literal["research-run-snapshot-v1"] | None = None
    dataset_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    configuration_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    pipeline_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    model: str | None = Field(default=None, min_length=1, max_length=200)
    routes: list[Literal["standard", "knowledge_collaboration"]] | None = Field(
        default=None, min_length=1, max_length=2
    )
    trials: list[ResearchTrial] = Field(max_length=400)
    attempts: list[ResearchTrial] | None = Field(default=None, max_length=MAX_RESEARCH_ATTEMPTS)

    @model_validator(mode="after")
    def manifest(self):
        if self.routes is not None and len(set(self.routes)) != len(self.routes):
            raise ValueError("Duplicate snapshot route")
        if self.version and any(
            value is None
            for value in (
                self.dataset_sha256,
                self.configuration_sha256,
                self.pipeline_sha256,
                self.model,
                self.routes,
                self.attempts,
            )
        ):
            raise ValueError("Versioned snapshots require a complete execution manifest")
        return self


class ClaimReview(StrictModel):
    claim_id: str
    support: Literal["supported", "unsupported", "uncertain"] | None = None


class RequirementReview(StrictModel):
    requirement_id: str
    status: Literal["satisfied", "partial", "missing", "uncertain"] | None = None
    claim_ids: list[str] = Field(default_factory=list, max_length=10)


class TrialReview(StrictModel):
    case_id: str
    route: Literal["standard", "knowledge_collaboration"]
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer: str | None = Field(default=None, min_length=1, max_length=100)
    claims: list[ClaimReview] = Field(default_factory=list, max_length=10)
    requirements: list[RequirementReview] = Field(default_factory=list, max_length=20)
    abstention: Literal["correct", "incorrect", "uncertain"] | None = None
