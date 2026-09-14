"""Public configuration contracts. No endpoints, credentials or local paths."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.conversation_context import ContextUsage
from app.schemas.memory import MemoryUsage


class GenerationOptions(BaseModel):
    model_config = ConfigDict(strict=True, allow_inf_nan=False, extra="forbid")

    model: str | None = Field(default=None, min_length=1, max_length=100)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_output_tokens: int | None = Field(default=None, ge=256, le=32000)
    thinking_effort: Literal["low", "medium", "high", "off"] | None = None


class EffectiveGenerationConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    temperature: float | None = None
    top_p: float | None = None
    # Old answers may not have recorded a cap; never invent historical metadata.
    max_output_tokens: int | None = Field(default=None, ge=256, le=32000)
    thinking_effort: Literal["low", "medium", "high"] | None = None
    policy_version: str

    def provider_settings(self, *, include_output_limit: bool = True) -> dict:
        result = {}
        if include_output_limit and self.max_output_tokens is not None:
            # PydanticAI maps max_tokens to Responses.max_output_tokens.
            result["max_tokens"] = self.max_output_tokens
        if self.top_p is not None:
            result["top_p"] = self.top_p
        if self.temperature is not None:
            result["temperature"] = self.temperature
        if self.thinking_effort is not None:
            result["openai_reasoning_effort"] = self.thinking_effort
            result["openai_reasoning_summary"] = "auto"
        return result


class EffectiveAnswerConfig(EffectiveGenerationConfig):
    """Actual answer metadata, independent of provider generation parameters."""

    memory: MemoryUsage | None = None
    context: ContextUsage | None = None


class GenerationModelInfo(BaseModel):
    id: str
    temperature: bool
    top_p: bool = False
    # A bounded output budget is supported by the Responses transport for all models.
    output_token_limits: tuple[int, int] = (256, 8000)
    thinking_efforts: list[str]
    defaults: EffectiveGenerationConfig
    status: Literal["configured", "unconfigured"]


class LocalModelInfo(BaseModel):
    id: str
    runtime: str
    dimension: int | None = None
    revision: str | None = None
    status: Literal["not_checked", "healthy", "unavailable", "version_mismatch"]
    checked_at: str | None = None


class CapabilityInfo(BaseModel):
    id: str
    available: bool
    execution: Literal["agent_tool", "session_service", "background_worker", "unavailable"]


class GenerationConfigResponse(BaseModel):
    default: str
    models: list[GenerationModelInfo]
    policy_version: str


class AgentCapabilitiesResponse(GenerationConfigResponse):
    embedding: LocalModelInfo
    rerank: LocalModelInfo
    capabilities: list[CapabilityInfo]
