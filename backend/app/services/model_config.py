"""One server policy for discovery and all generation paths."""

import hashlib
import json

from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.schemas.model_config import (
    EffectiveGenerationConfig,
    GenerationConfigResponse,
    GenerationModelInfo,
    GenerationOptions,
)


def allowed_models() -> list[str]:
    # The deployment's explicit default is also an authorized selection.
    return list(dict.fromkeys([settings.AI_MODEL, *settings.AI_AVAILABLE_MODELS]))


def model_controls(model: str) -> list[str]:
    # Exact deployment policy, never infer capabilities from a model name prefix.
    return settings.AI_MODEL_CONTROLS.get(model, [])


def output_token_limit(model: str) -> int:
    return max(256, min(32000, settings.AI_MODEL_OUTPUT_LIMITS.get(model, 8000)))


def policy_version() -> str:
    payload = {
        "models": allowed_models(),
        "controls": settings.AI_MODEL_CONTROLS,
        "temperature": settings.AI_TEMPERATURE,
        "thinking_enabled": settings.AI_THINKING_ENABLED,
        "thinking_effort": settings.AI_THINKING_EFFORT,
        "output_tokens": {"default": 8000, "min": 256, "max": 32000},
        "model_output_limits": settings.AI_MODEL_OUTPUT_LIMITS,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def generation_config() -> GenerationConfigResponse:
    """Read deployment policy without probing tools, loading models or doing I/O."""
    return GenerationConfigResponse(
        default=settings.AI_MODEL,
        policy_version=policy_version(),
        models=[
            GenerationModelInfo(
                id=model,
                temperature="temperature" in model_controls(model),
                top_p="top_p" in model_controls(model),
                output_token_limits=(256, output_token_limit(model)),
                thinking_efforts=["low", "medium", "high"]
                if "thinking_effort" in model_controls(model)
                else [],
                defaults=resolve_generation_config({"model": model}),
                status="configured" if settings.OPENAI_API_KEY else "unconfigured",
            )
            for model in allowed_models()
        ],
    )


def resolve_generation_config(data: dict) -> EffectiveGenerationConfig:
    try:
        options = GenerationOptions.model_validate(data)
    except ValidationError as exc:
        raise BadRequestError(message="模型参数格式无效，请检查数值范围与推理强度") from exc
    model = options.model or settings.AI_MODEL
    if model not in allowed_models():
        raise BadRequestError(message="该模型未获授权，请从模型列表重新选择")
    controls = model_controls(model)
    if options.max_output_tokens is not None and options.max_output_tokens > output_token_limit(
        model
    ):
        raise BadRequestError(
            message=f"当前模型输出上限为 {output_token_limit(model)} Token，请调整设置"
        )
    temperature = options.temperature
    if options.top_p is not None and "top_p" not in controls:
        raise BadRequestError(message="当前模型未开放 Top P 设置，请恢复默认值")
    if options.top_p is not None and temperature is not None:
        raise BadRequestError(message="温度和 Top P 请选择一项调整，另一项恢复默认")
    if temperature is not None and "temperature" not in controls:
        raise BadRequestError(message="当前模型未开放温度设置，请恢复默认值")
    if temperature is None and options.top_p is None and "temperature" in controls:
        temperature = settings.AI_TEMPERATURE
    effort = options.thinking_effort
    if effort not in (None, "off") and "thinking_effort" not in controls:
        raise BadRequestError(message="当前模型未开放推理强度设置，请恢复默认值")
    if effort is None and settings.AI_THINKING_ENABLED and "thinking_effort" in controls:
        effort = settings.AI_THINKING_EFFORT
    return EffectiveGenerationConfig(
        model=model,
        temperature=temperature,
        top_p=options.top_p,
        max_output_tokens=options.max_output_tokens or min(8000, output_token_limit(model)),
        thinking_effort=None if effort == "off" else effort,
        policy_version=policy_version(),
    )
