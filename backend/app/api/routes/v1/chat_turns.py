"""Normal conversations use durable turns; closing HTTP never cancels execution."""

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import CurrentUser, DBSession
from app.api.project_deps import CurrentProject
from app.schemas.agent_run import AgentRunResponse
from app.schemas.chat_turn import ChatTurnCreate
from app.services.chat_turn import ChatTurnService
from app.services.document_export import ExportRequest
from app.services.message_export import export_message

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/messages/{message_id}/export")
async def download_answer(
    message_id: UUID,
    data: ExportRequest,
    user: CurrentUser,
    db: DBSession,
    project_id: CurrentProject,
):
    file = await export_message(db, user.id, project_id, message_id, data.format)
    return Response(
        file["content"],
        media_type=file["mime_type"],
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file['name'])}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


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


@router.get("/conversations/{conversation_id}/messages/{answer_id}/context")
async def context_sources(
    response: Response,
    conversation_id: UUID,
    answer_id: UUID,
    user: CurrentUser,
    db: DBSession,
    project_id: CurrentProject,
):
    from app.services.conversation_context import read_references

    response.headers["Cache-Control"] = "private, no-store"
    return await read_references(db, user.id, project_id, conversation_id, answer_id)
