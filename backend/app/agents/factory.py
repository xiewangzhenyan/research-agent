"""One role factory; delegates execution to the native graph/model primitives."""

from dataclasses import dataclass, field

from pydantic import BaseModel

from app.agents.model import build_model, structured_call
from app.agents.policy import ExecutionLimits
from app.schemas.model_config import EffectiveGenerationConfig


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    system_prompt: str
    output_schema: type[BaseModel] | None = None
    limits: ExecutionLimits = field(default_factory=ExecutionLimits)
    output_tokens: int | None = None
    retries: int = 0


@dataclass(frozen=True)
class ConfiguredAgent:
    definition: AgentDefinition
    configuration: EffectiveGenerationConfig
    model: object

    def registry(self, deps=None):
        from app.agents.runtime import ToolRegistry

        if self.definition.output_schema is not None:
            raise ValueError("Structured roles cannot acquire executable tools")
        registry = ToolRegistry(self.model, self.configuration, self.definition.system_prompt, deps)
        registry.limits = self.definition.limits
        return registry

    async def structured(self, prompt, *, usage=None, validate=None, request_limit=None):
        definition = self.definition
        if definition.output_schema is None:
            raise ValueError("This agent has no structured output schema")
        limits = definition.limits
        output_limit = self.configuration.max_output_tokens or 8000
        if definition.output_tokens is not None:
            output_limit = min(output_limit, definition.output_tokens)
        return await structured_call(
            self.model,
            definition.output_schema,
            definition.system_prompt,
            prompt,
            self.configuration,
            usage=usage,
            validate=validate,
            retries=definition.retries,
            request_limit=min(request_limit, limits.requests)
            if request_limit is not None
            else limits.requests,
            token_limit=limits.tokens,
            model_settings={"max_tokens": output_limit, "timeout": limits.timeout},
        )


def create_agent(definition, configuration, *, model=None):
    return ConfiguredAgent(
        definition, configuration, model if model is not None else build_model(configuration.model)
    )
