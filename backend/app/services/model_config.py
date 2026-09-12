"""One server policy for discovery and all generation paths."""

import hashlib
import json

from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.schemas.model_config import EffectiveGenerationConfig, GenerationOptions


def allowed_models() -> list[str]:
    # The deployment's explicit default is also an authorized selection.
    return list(dict.fromkeys([settings.AI_MODEL, *settings.AI_AVAILABLE_MODELS]))


def model_controls(model: str) -> list[str]:
    # Exact deployment policy, never infer capabilities from a model name prefix.
    return settings.AI_MODEL_CONTROLS.get(model, [])


def policy_version() -> str:
    payload = {
        "models": allowed_models(),
        "controls": settings.AI_MODEL_CONTROLS,
        "temperature": settings.AI_TEMPERATURE,
        "thinking_enabled": settings.AI_THINKING_ENABLED,
        "thinking_effort": settings.AI_THINKING_EFFORT,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def resolve_generation_config(data: dict) -> EffectiveGenerationConfig:
    try:
        options = GenerationOptions.model_validate(data)
    except ValidationError as exc:
        raise BadRequestError(message="模型参数格式无效，请检查模型、温度和推理强度") from exc
    model = options.model or settings.AI_MODEL
    if model not in allowed_models():
        raise BadRequestError(message="该模型未获授权，请从模型列表重新选择")
    controls = model_controls(model)
    temperature = options.temperature
    if temperature is not None and "temperature" not in controls:
        raise BadRequestError(message="当前模型未开放温度设置，请恢复默认值")
    if temperature is None and "temperature" in controls:
        temperature = settings.AI_TEMPERATURE
    effort = options.thinking_effort
    if effort not in (None, "off") and "thinking_effort" not in controls:
        raise BadRequestError(message="当前模型未开放推理强度设置，请恢复默认值")
    if effort is None and settings.AI_THINKING_ENABLED and "thinking_effort" in controls:
        effort = settings.AI_THINKING_EFFORT
    return EffectiveGenerationConfig(
        model=model,
        temperature=temperature,
        thinking_effort=None if effort == "off" else effort,
        policy_version=policy_version(),
    )
