"""Normal conversations use durable turns; closing HTTP never cancels execution."""

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CurrentUser, DBSession
from app.api.project_deps import CurrentProject
from app.schemas.agent_run import AgentRunResponse
from app.schemas.chat_turn import ChatTurnCreate
from app.services.chat_turn import ChatTurnService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/turns", response_model=AgentRunResponse, status_code=201)
async def submit(
    data: ChatTurnCreate, user: CurrentUser, db: DBSession, project_id: CurrentProject
):
    return await ChatTurnService(db, user.id, project_id=project_id).create(data)


@router.get("/conversations/{conversation_id}/state")
async def state(
    conversation_id: UUID,
    user: CurrentUser,
    db: DBSession,
    project_id: CurrentProject,
    before: UUID | None = None,
    include_messages: bool = True,
):
    return await ChatTurnService(db, user.id, project_id=project_id).state(
        conversation_id, before=before, include_messages=include_messages
    )
