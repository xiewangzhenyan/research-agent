"""Public configuration contracts. No endpoints, credentials or local paths."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GenerationOptions(BaseModel):
    model_config = ConfigDict(strict=True, allow_inf_nan=False)

    model: str | None = Field(default=None, min_length=1, max_length=100)
    temperature: float | None = Field(default=None, ge=0, le=2)
    thinking_effort: Literal["low", "medium", "high", "off"] | None = None


class EffectiveGenerationConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    temperature: float | None = None
    thinking_effort: Literal["low", "medium", "high"] | None = None
    policy_version: str

    def provider_settings(self) -> dict:
        result = {}
        if self.temperature is not None:
            result["temperature"] = self.temperature
        if self.thinking_effort is not None:
            result["openai_reasoning_effort"] = self.thinking_effort
            result["openai_reasoning_summary"] = "auto"
        return result


class GenerationModelInfo(BaseModel):
    id: str
    temperature: bool
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


class AgentCapabilitiesResponse(BaseModel):
    default: str
    models: list[GenerationModelInfo]
    embedding: LocalModelInfo
    rerank: LocalModelInfo
    capabilities: list[CapabilityInfo]
    policy_version: str
