# ruff: noqa: RUF001 - Chinese user-facing text.
"""Accept chat turns atomically; execution belongs to the durable worker."""

import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select, tuple_
from sqlalchemy.orm import selectinload

from app.agents.tool_catalog import DURABLE_TOOL_NAMES, PYTHON_TOOL, TOOL_POLICY_VERSION
from app.core.exceptions import AlreadyExistsError, BadRequestError, NotFoundError, RateLimitError
from app.db.models.agent_run import AgentRun
from app.db.models.conversation import Message
from app.repositories import message_rating_repo
from app.repositories.agent_run import ACTIVE, AgentRunRepository
from app.schemas.agent_run import AgentRunResponse
from app.schemas.conversation import (
    ConversationCreate,
    ConversationUpdate,
    MessageCreate,
    MessageRead,
    ToolCallComplete,
    ToolCallCreate,
)
from app.services.conversation import ConversationService
from app.services.knowledge import KnowledgeService
from app.services.knowledge_citations import persist_citations
from app.services.model_config import resolve_generation_config
from app.services.project import ProjectService
from app.services.retrieval_snapshot import capture


class ChatTurnService:
    def __init__(self, db, user_id, *, project_id=None):
        self.db, self.user_id, self.project_id = db, user_id, project_id
        self.repo = AgentRunRepository(db)
        self.conversations = ConversationService(db, project_id=project_id)

    async def create(self, data):
        projects = ProjectService(self.db, self.user_id)
        await projects.validate(self.project_id)
        payload = data.model_dump(mode="json", exclude={"idempotency_key"}, exclude_unset=True)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        user = await self.repo.account_lock(self.user_id)
        previous = await self.repo.by_key(self.user_id, data.idempotency_key)
        if previous:
            if (
                previous.project_id != self.project_id
                or previous.request_hash != digest
                or not previous.conversation_id
            ):
                raise AlreadyExistsError(message="发送标识已用于其他内容，请重新发送")
            return previous
        conversation = (
            await self.conversations.get_conversation(
                data.conversation_id, user_id=self.user_id, access="owner"
            )
            if data.conversation_id
            else None
        )
        from app.services.work_task import CONTROLS, WorkTaskService

        work = WorkTaskService(self.db, self.user_id, project_id=self.project_id)
        selection = await work.select(data, data.conversation_id)
        if selection and selection["action"] in {*CONTROLS, "clarify"}:
            return await self.control_turn(data, conversation, selection, digest, work)
        if (
            selection
            and selection["action"] in {"new", "revise", "replace"}
            and not data.message.strip()
        ):
            raise BadRequestError(message="请输入完整任务目标或修改要求")
        bases = data.knowledge_base_ids
        if bases is None:
            bases = [
                UUID(v)
                for v in (
                    conversation.active_knowledge_base_ids
                    if conversation
                    else await projects.defaults(self.project_id)
                )
            ]
        documents = data.knowledge_document_ids
        if "knowledge_document_ids" not in data.model_fields_set and conversation:
            documents = (
                [UUID(v) for v in conversation.active_knowledge_document_ids]
                if conversation.active_knowledge_document_ids is not None
                else None
            )
        strict = data.knowledge_strict
        if strict is None:
            strict = conversation.knowledge_strict if conversation else True
        knowledge = KnowledgeService(self.db, self.user_id)
        await knowledge.validate_scope(bases, documents, require_ready=True)
        if bases and (not data.message.strip() or len(data.message) > 1500):
            raise BadRequestError(message="知识库问题需为 1–1500 字")
        if bases and strict and data.file_ids:
            raise BadRequestError(
                message="严格资料模式仅使用选定知识库，请先导入附件或关闭严格模式"
            )
        files = [str(v) for v in data.file_ids]
        if files:
            attached = await self.conversations.list_attached_files(files, user_id=self.user_id)
            if sum(f.size for f in attached) > 20 * 1024 * 1024:
                raise BadRequestError(message="单次对话附件合计最多 20 MiB，请拆分后发送")
            if sum(len(f.parsed_content or "") for f in attached) > 60000:
                raise BadRequestError(message="附件文本过长，请导入知识库后提问")
        generation = (
            data.generation.model_dump(exclude_none=True)
            if data.generation is not None
            else (conversation.generation_options or {})
            if conversation
            else {}
        )
        configuration = resolve_generation_config(generation)
        from app.services.context_budget import check_prompt

        check_prompt(data.message, configuration)
        if conversation is None:
            conversation = await self.conversations.create_conversation(
                ConversationCreate(user_id=self.user_id, title=data.message[:50] or "附件对话")
            )
        await self.conversations.update_conversation(
            conversation.id,
            ConversationUpdate(
                active_knowledge_base_ids=bases,
                active_knowledge_document_ids=documents,
                knowledge_strict=strict,
            ),
            user_id=self.user_id,
        )
        # Same transaction as the accepted message; runs retain their own immutable snapshot.
        conversation.generation_options = generation
        sent_at = datetime.now(UTC)
        user_message = await self.conversations.add_message(
            conversation.id, MessageCreate(role="user", content=data.message), user_id=self.user_id
        )
        user_message.created_at = sent_at
        if files:
            await self.conversations.link_files_to_message(
                user_message.id, files, user_id=self.user_id
            )
        assistant = await self.conversations.add_message(
            conversation.id,
            MessageCreate(
                role="assistant",
                content="",
                model_name=configuration.model,
                effective_config=configuration.model_dump(),
            ),
            user_id=self.user_id,
        )
        assistant.created_at = sent_at + timedelta(microseconds=1)
        request = {
            "kind": "chat",
            "clarification_policy": "clarification-v1",
            "prompt": data.message,
            "file_ids": files,
            "knowledge_base_ids": [str(v) for v in bases],
            "knowledge_document_ids": [str(v) for v in documents]
            if documents is not None
            else None,
            "knowledge_strict": strict,
            "tools": list(DURABLE_TOOL_NAMES),
            "tool_policy_version": TOOL_POLICY_VERSION,
            "conversation_id": str(conversation.id),
            "user_message_id": str(user_message.id),
        }
        from app.services.capability_assets import CapabilityService
        from app.services.capability_runtime import snapshot

        request["capabilities"] = await snapshot(CapabilityService(self.db, user, self.project_id))
        if data.python_enabled:
            from app.services import sandbox_client
            from app.services.sandbox_files import load_inputs
            from app.services.tool_policy import resolve_tools

            if bases and strict:
                raise BadRequestError(
                    message="严格资料模式不执行代码，请关闭严格模式后使用计算工具"
                )
            request["tools"] = await resolve_tools(user, [*DURABLE_TOOL_NAMES, PYTHON_TOOL])
            health = await sandbox_client.health()
            request["sandbox_protocol"] = 2 if health.get("file_execution") else 1
            if files and request["sandbox_protocol"] != 2:
                raise BadRequestError(message="当前沙箱不支持文件计算")
            request["input_file_ids"] = files
            _, request["input_snapshot"] = await load_inputs(self.db, self.user_id, files)
        if bases:
            request["retrieval_snapshot"] = capture(
                await knowledge.get_retrieval_config(), override=False, collaboration=False
            )
        run = await self.repo.add(
            AgentRun(
                user_id=self.user_id,
                project_id=self.project_id,
                conversation_id=conversation.id,
                user_message_id=user_message.id,
                assistant_message_id=assistant.id,
                idempotency_key=data.idempotency_key,
                request_hash=digest,
                request=request,
                effective_config=configuration.model_dump(),
                created_at=sent_at,
            )
        )
        await work.attach(selection, run, user_message)
        if await self.repo.active_count(self.user_id) > 5:
            raise RateLimitError(message="最多同时保留 5 条待完成的请求，请等待或停止已有请求")
        if selection:
            from app.services.context_budget import envelope

            envelope(
                {**run.request, "work_context": await work.context(run.request)}, configuration
            )
        from app.services.memory_extraction import enqueue

        await enqueue(
            self.db,
            self.user_id,
            self.project_id,
            user_message,
            strict_knowledge=bool(bases and strict),
        )
        await self.repo.event(run, "queued", {"message": "消息已保存，关闭页面后仍会继续处理"})
        return run

    async def control_turn(self, data, conversation, selection, request_hash, work):
        """Controls do not queue behind HITL, require a model, or consume a run slot."""
        from app.db.models.work_task import WorkTaskConversation
        from app.schemas.work_task import WorkTaskControl
        from app.services.work_task import CONTROL_TEXT

        if data.file_ids:
            raise BadRequestError(message="暂停、取消和完成操作不接收附件，请单独发送附件")
        action = selection["action"]
        task = None
        if action != "clarify":
            task = await work.control(
                selection["task_id"],
                WorkTaskControl(
                    operation_id=data.idempotency_key,
                    expected_revision=selection["expected_revision"],
                    action=action,
                ),
            )
        if conversation is None:
            conversation = await self.conversations.create_conversation(
                ConversationCreate(user_id=self.user_id, title=data.message[:50])
            )
        if task and await self.db.get(WorkTaskConversation, (task.id, conversation.id)) is None:
            self.db.add(WorkTaskConversation(task_id=task.id, conversation_id=conversation.id))
        text = (
            CONTROL_TEXT[action]
            if task
            else "有多个未结束任务，请展开聊天中的任务卡片，选择要继续或修改的任务。"
        )
        sent_at = datetime.now(UTC)
        message = await self.conversations.add_message(
            conversation.id, MessageCreate(role="user", content=data.message), user_id=self.user_id
        )
        message.created_at = sent_at
        answer = await self.conversations.add_message(
            conversation.id, MessageCreate(role="assistant", content=text), user_id=self.user_id
        )
        answer.created_at = sent_at + timedelta(microseconds=1)
        run = await self.repo.add(
            AgentRun(
                user_id=self.user_id,
                project_id=self.project_id,
                conversation_id=conversation.id,
                user_message_id=message.id,
                assistant_message_id=answer.id,
                idempotency_key=data.idempotency_key,
                request_hash=request_hash,
                request={"kind": "work_control", "prompt": data.message, "action": action},
                effective_config={},
                status="completed",
                result={"content": text},
                created_at=sent_at,
                finished_at=sent_at,
            )
        )
        await self.repo.event(run, "completed", {"message": text})
        return run

    async def state(self, conversation_id, *, before=None, include_messages=True):
        conversation = await self.conversations.get_conversation(
            conversation_id, user_id=self.user_id, access="owner"
        )
        query_runs = select(AgentRun).where(
            AgentRun.conversation_id == conversation_id,
            AgentRun.user_id == self.user_id,
            AgentRun.project_id == self.project_id,
        )
        recent_ids = (
            query_runs.with_only_columns(AgentRun.id)
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .limit(30)
        )
        runs = list(
            await self.db.scalars(
                query_runs.where(
                    or_(AgentRun.id.in_(recent_ids), AgentRun.status.in_(ACTIVE))
                ).order_by(AgentRun.created_at, AgentRun.id)
            )
        )
        result = {"runs": public_runs(runs), "generation": conversation.generation_options or {}}
        if not include_messages:
            return result
        query = select(Message).where(Message.conversation_id == conversation_id)
        if before:
            cursor = await self.db.get(Message, before)
            if not cursor or cursor.conversation_id != conversation_id:
                raise NotFoundError(message="历史消息位置已失效，请刷新")
            query = query.where(
                tuple_(Message.created_at, Message.id) < (cursor.created_at, cursor.id)
            )
        items = list(
            await self.db.scalars(
                query.options(selectinload(Message.files), selectinload(Message.tool_calls))
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(51)
            )
        )
        more = len(items) > 50
        items = list(reversed(items[:50]))
        ids = [m.id for m in items]
        page_runs = (
            list(await self.db.scalars(query_runs.where(AgentRun.assistant_message_id.in_(ids))))
            if ids
            else []
        )
        result["runs"] = public_runs(list({r.id: r for r in [*page_runs, *runs]}.values()))
        ratings = (
            await message_rating_repo.get_user_ratings_for_messages(
                self.db, message_ids=ids, user_id=self.user_id
            )
            if ids
            else {}
        )
        counts = (
            await message_rating_repo.get_rating_counts_for_messages(self.db, message_ids=ids)
            if ids
            else {}
        )
        result["messages"] = [
            MessageRead.model_validate(m).model_copy(
                update={"user_rating": ratings.get(m.id), "rating_count": counts.get(m.id)}
            )
            for m in items
        ]
        result["before"] = str(items[0].id) if more else None
        return result


def public_runs(runs):
    return [
        {
            **AgentRunResponse.model_validate(run).model_dump(exclude={"request", "result"}),
            "request": {"routing": run.request.get("routing")},
            "result": run.result
            if run.status in ("running", "waiting_input", "cancelling")
            else None,
        }
        for run in sorted(runs, key=lambda r: (r.created_at, r.id))
    ]


async def save_chat_result(db, run, result):
    """Called inside the worker's fenced completion transaction, exactly once."""
    service = ConversationService(db, project_id=run.project_id)
    await service.get_conversation(run.conversation_id, user_id=run.user_id, access="owner")
    message = await db.get(Message, run.assistant_message_id)
    if not message or message.conversation_id != run.conversation_id:
        raise NotFoundError(message="会话消息已删除")
    message.content, message.thinking = result["content"], result.get("thinking") or None
    message.effective_config = result.get("effective_config") or run.effective_config
    calls = copy.deepcopy(result.get("tool_calls", []))
    if result.get("citations"):
        sources = copy.deepcopy(result["citations"])
        for source in sources:
            source["citation_id"] = str(uuid4())
        calls.insert(
            0,
            {
                "tool_call_id": str(uuid4()),
                "tool_name": "search_knowledge_base",
                "args": {"query": run.request["prompt"]},
                "result": json.dumps(
                    {"items": sources, "retrieval": result.get("retrieval", {})}, ensure_ascii=False
                ),
            },
        )
        await persist_citations(db, run.conversation_id, message.id, calls)
        # Public run state and events must not retain a second copy of source text.
        result["citations"] = json.loads(calls[0]["result"])["items"]
    for call in calls:
        tool = await service.start_tool_call(
            message.id,
            ToolCallCreate(
                tool_call_id=call["tool_call_id"],
                tool_name=call["tool_name"],
                args=call.get("args") or {},
            ),
        )
        await service.complete_tool_call(
            tool.id, ToolCallComplete(result=call.get("result") or "", success=True)
        )
    result.pop("tool_calls", None)
    await db.flush()
    from app.services.conversation_context import enqueue

    await enqueue(db, run.conversation_id, run.effective_config)
