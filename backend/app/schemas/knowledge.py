"""Validated native knowledge processing settings."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChunkingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Bound character windows for the current local encoder, not upstream defaults.
    chunk_size: int = Field(default=450, ge=256, le=500, strict=True)
    chunk_overlap: int = Field(default=65, ge=0, le=128, strict=True)

    @model_validator(mode="after")
    def validate_overlap(self):
        if self.chunk_overlap * 2 >= self.chunk_size:
            raise ValueError("重叠长度必须小于片段长度的一半")
        return self


class RetrievalConfig(BaseModel):
    """Account defaults and per-request experiments share one validated contract."""

    model_config = ConfigDict(extra="forbid")
    mode: Literal["hybrid", "keyword", "semantic"] = "hybrid"
    candidate_limit: int = Field(default=30, ge=10, le=100, strict=True)
    result_limit: int = Field(default=6, ge=1, le=10, strict=True)
    semantic_threshold: float = Field(default=0.45, ge=0, le=1, strict=True)
    keyword_threshold: float = Field(default=0, ge=0, le=100, strict=True)
    semantic_weight: float = Field(default=1, ge=0, le=2, strict=True)
    keyword_weight: float = Field(default=1, ge=0, le=2, strict=True)
    rrf_k: int = Field(default=60, ge=10, le=100, strict=True)
    rerank_enabled: bool = Field(default=False, strict=True)
    rerank_limit: int = Field(default=10, ge=10, le=20, strict=True)
    context_enabled: bool = Field(default=False, strict=True)
    context_window: int = Field(default=1, ge=1, le=2, strict=True)
    context_char_budget: int = Field(default=1000, ge=500, le=2000, strict=True)

    @model_validator(mode="after")
    def validate_weights(self):
        if self.mode == "hybrid" and self.semantic_weight + self.keyword_weight == 0:
            raise ValueError("混合检索至少需要一个大于零的权重")
        return self


class RetrievalSnapshot(BaseModel):
    """Server-generated immutable parameter record; resource grants stay separate."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    configuration_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    origin: Literal["account", "task_override"]
    config: RetrievalConfig
    result_limit_capped: bool = False
