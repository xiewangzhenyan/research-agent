"""Export owned, completed answers without another model request."""

from sqlalchemy import select

from app.core.exceptions import BadRequestError
from app.db.models.agent_run import AgentRun
from app.db.models.knowledge import KnowledgeCitation
from app.services.conversation import ConversationService
from app.services.document_export import DocumentRequest, render_async
from app.services.knowledge_citations import read_citation


async def export_message(db, user_id, project_id, message_id, format):
    service = ConversationService(db, project_id=project_id)
    message = await service.get_message(message_id)
    conversation = await service.get_conversation(
        message.conversation_id, user_id=user_id, access="owner"
    )
    if message.role != "assistant" or not message.content.strip():
        raise BadRequestError(message="只有已完成的回答可以导出")
    run = await db.scalar(select(AgentRun).where(AgentRun.assistant_message_id == message_id))
    if run and run.status != "completed":
        raise BadRequestError(message="请等待回答完成后导出")
    content = message.content
    ids = list(
        await db.scalars(
            select(KnowledgeCitation.id)
            .where(KnowledgeCitation.message_id == message_id, KnowledgeCitation.user_id == user_id)
            .limit(20)
        )
    )
    sources = [await read_citation(db, user_id, cid) for cid in ids]
    if sources:
        content += "\n\n## 引用来源\n"
        for source in sorted(sources, key=lambda source: source.get("index") or 0):
            title = source.get("title", "引用资料")
            page = f"，第 {source['page']} 页" if source.get("page") else ""
            content += f"\n[{source.get('index', '?')}] {title}{page}\n"
            if source.get("state") != "deleted" and source.get("content"):
                content += f"\n> {source['content'][:2000].replace(chr(10), chr(10) + '> ')}\n"
    # Validation before worker-thread rendering, including appended citation text.
    if len(content) > 100000:
        raise BadRequestError(message="回答与引用合计超过 10 万字符，请拆分导出")
    return await render_async(
        DocumentRequest(
            format=format, title=(conversation.title or "对话回答")[:120], content=content
        )
    )
