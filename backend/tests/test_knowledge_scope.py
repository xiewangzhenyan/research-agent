"""Document scope must fail closed when any selected document is unavailable."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import BadRequestError, NotFoundError
from app.schemas.conversation import ConversationUpdate
from app.services.knowledge import KnowledgeService
from app.services.knowledge_index import MODEL


@pytest.mark.anyio
async def test_scope_validates_all_document_ids_before_retrieval():
    user, base, owned, foreign = [uuid4() for _ in range(4)]
    db = AsyncMock()
    db.scalars.return_value = [SimpleNamespace(id=owned, status="ready", embedding_model=MODEL)]
    service = KnowledgeService(db, user)
    service.get_base = AsyncMock()
    with pytest.raises(NotFoundError):
        await service.validate_scope([base], [owned, foreign], require_ready=True)
    await service.validate_scope([base], [owned], require_ready=True)


@pytest.mark.anyio
async def test_empty_or_unready_scope_never_becomes_full_base_search():
    db = AsyncMock()
    user, base, doc = [uuid4() for _ in range(3)]
    service = KnowledgeService(db, user)
    service.get_base = AsyncMock()
    with pytest.raises(BadRequestError):
        await service.validate_scope([base], [])
    with pytest.raises(BadRequestError):
        await service.validate_scope([], [doc])
    db.scalars.return_value = [SimpleNamespace(id=doc, status="embedding", embedding_model=MODEL)]
    with pytest.raises(BadRequestError):
        await service.validate_scope([base], [doc], require_ready=True)
    await service.validate_scope([base], [doc], require_ready=False)


def test_document_scope_requires_an_explicit_nonempty_list_or_null():
    assert ConversationUpdate().active_knowledge_document_ids is None
    assert ConversationUpdate(active_knowledge_document_ids=None).model_dump(
        exclude_unset=True
    ) == {"active_knowledge_document_ids": None}
    for ids in [[], [uuid4() for _ in range(6)]]:
        with pytest.raises(ValidationError):
            ConversationUpdate(active_knowledge_document_ids=ids)
