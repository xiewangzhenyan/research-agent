"""Request-scoped project selection. An absent header never means all projects."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header

from app.api.deps import CurrentUser, DBSession
from app.services.conversation import ConversationService
from app.services.project import ProjectService


async def current_project(
    db: DBSession,
    user: CurrentUser,
    x_project_id: Annotated[UUID | None, Header()] = None,
) -> UUID | None:
    await ProjectService(db, user.id).validate(x_project_id)
    return x_project_id


CurrentProject = Annotated[UUID | None, Depends(current_project)]


def scoped_conversation_service(db: DBSession, project_id: CurrentProject):
    return ConversationService(db, project_id=project_id)


ScopedConversationSvc = Annotated[ConversationService, Depends(scoped_conversation_service)]
