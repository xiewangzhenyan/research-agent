"""Read-only capability discovery with bounded, cached local health checks."""

import asyncio
import time
from datetime import UTC, datetime

import httpx

from app.agents.tool_catalog import CHAT_TOOL_NAMES
from app.core.config import settings
from app.schemas.model_config import (
    AgentCapabilitiesResponse,
    CapabilityInfo,
    GenerationModelInfo,
    LocalModelInfo,
)
from app.services.knowledge_enrichment import RERANK_MODEL, RERANK_REVISION
from app.services.knowledge_index import MODEL
from app.services.model_config import (
    allowed_models,
    model_controls,
    policy_version,
    resolve_generation_config,
)

_health_lock = asyncio.Lock()
_health_cache: tuple[str, float, LocalModelInfo] | None = None


async def rerank_health() -> LocalModelInfo:
    global _health_cache
    async with _health_lock:
        endpoint = settings.RAG_RERANK_URL
        if _health_cache and _health_cache[0] == endpoint and time.monotonic() < _health_cache[1]:
            return _health_cache[2]
        status = "unavailable"
        try:
            async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
                response = await client.get(endpoint.rstrip("/") + "/health")
                response.raise_for_status()
                data = response.json()
            if data.get("status") == "healthy":
                status = (
                    "healthy"
                    if data.get("model") == RERANK_MODEL and data.get("revision") == RERANK_REVISION
                    else "version_mismatch"
                )
        except (httpx.HTTPError, ValueError, AttributeError):
            pass  # Never expose response bodies, internal addresses or credentials.
        result = LocalModelInfo(
            id=RERANK_MODEL,
            runtime="ONNX / CPU",
            revision=RERANK_REVISION,
            status=status,
            checked_at=datetime.now(UTC).isoformat(),
        )
        _health_cache = (endpoint, time.monotonic() + 30, result)
        return result


async def get_capabilities(user=None) -> AgentCapabilitiesResponse:
    from app.services.tool_policy import tool_catalog

    tools = await tool_catalog(user)
    python_available = next(
        item["available"] for item in tools["items"] if item["id"] == "run_python"
    )
    return AgentCapabilitiesResponse(
        default=settings.AI_MODEL,
        policy_version=policy_version(),
        models=[
            GenerationModelInfo(
                id=model,
                temperature="temperature" in model_controls(model),
                thinking_efforts=["low", "medium", "high"]
                if "thinking_effort" in model_controls(model)
                else [],
                defaults=resolve_generation_config({"model": model}),
                status="configured" if settings.OPENAI_API_KEY else "unconfigured",
            )
            for model in allowed_models()
        ],
        # Encoder loads on demand in API/ingestion processes. Do not load another
        # copy or claim all workers are healthy based on this API process.
        embedding=LocalModelInfo(
            id=MODEL, runtime="FastEmbed / CPU", dimension=512, status="not_checked"
        ),
        rerank=await rerank_health(),
        capabilities=[
            *[
                CapabilityInfo(id=name, available=True, execution="agent_tool")
                for name in CHAT_TOOL_NAMES
            ],
            CapabilityInfo(id="knowledge_retrieval", available=True, execution="session_service"),
            CapabilityInfo(id="durable_tasks", available=True, execution="background_worker"),
            CapabilityInfo(
                id="knowledge_collaboration", available=True, execution="background_worker"
            ),
            CapabilityInfo(
                id="run_python",
                available=python_available,
                execution="background_worker" if python_available else "unavailable",
            ),
            *[
                CapabilityInfo(id=name, available=False, execution="unavailable")
                for name in (
                    "create_chart",
                    "web_search",
                    "multi_agent",
                )
            ],
        ],
    )
