# Route is lifecycle plumbing only — auth, accept, dispatch loop, disconnect.
# Per-turn orchestration lives in app.services.agent_session.AgentSession.
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import CurrentUser, CurrentUserWS
from app.core.config import settings
from app.schemas.base import AgentModelsResponse
from app.schemas.model_config import AgentCapabilitiesResponse
from app.services.agent import AgentConnectionManager
from app.services.agent_capabilities import get_capabilities
from app.services.agent_session import AgentSession
from app.services.model_config import allowed_models

logger = logging.getLogger(__name__)

router = APIRouter()

manager = AgentConnectionManager()


@router.get("/agent/models", response_model=AgentModelsResponse)
async def list_models() -> dict[str, Any]:
    """Return available LLM models and the current default."""
    return {
        "default": settings.AI_MODEL,
        "models": allowed_models(),
    }


@router.get("/agent/capabilities", response_model=AgentCapabilitiesResponse)
async def capabilities(user: CurrentUser) -> AgentCapabilitiesResponse:
    """Expose only authenticated, redacted deployment configuration."""
    return await get_capabilities(user)


@router.websocket("/ws/agent")
async def agent_websocket(
    websocket: WebSocket,
    user: CurrentUserWS,
) -> None:
    if user is None:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await manager.connect(websocket)
    session = AgentSession(
        websocket,
        user,
    )

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            await session.handle_frame(data)
    finally:
        await session.shutdown()
        manager.disconnect(websocket)
