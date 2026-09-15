"""Authorized task submission, cancellation and durable human replies."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid5

from app.agents.tool_catalog import PYTHON_TOOL, TOOL_POLICY_VERSION
from app.core.exceptions import AlreadyExistsError, BadRequestError, NotFoundError, RateLimitError
from app.db.models.agent_run import AgentRun
from app.repositories.agent_run import TERMINAL, AgentRunRepository
from app.services import sandbox_client
from app.services.knowledge import KnowledgeService
from app.services.model_config import resolve_generation_config
from app.services.retrieval_snapshot import capture
from app.services.sandbox_files import load_inputs
from app.services.tool_policy import resolve_tools


class AgentRunService:
    def __init__(self, db, user_id, *, project_id=None):
        self.db, self.user_id = db, user_id
        self.repo = AgentRunRepository(db)
        self.project_id = project_id

    async def get(self, run_id, *, lock=False):
        run = await self.repo.get(run_id, self.user_id, lock=lock)
        if run is None or run.project_id != self.project_id:
            raise NotFoundError(message="任务不存在或无权访问")
        return run

    async def create(self, data):
        from app.services.project import ProjectService

        projects = ProjectService(self.db, self.user_id)
        await projects.validate(self.project_id)
        request = data.model_dump(mode="json", exclude={"idempotency_key"})
        if data.retrieval_config is None:
            request.pop("retrieval_config", None)
        if data.tools is None:
            request.pop("tools", None)
        if data.mode == "standard":
            request.pop("mode", None)  # Preserve existing clients' idempotency hashes.
        if not data.input_file_ids:
            request.pop("input_file_ids", None)
        request_hash = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        user = await self.repo.account_lock(self.user_id)
        existing = await self.repo.by_key(self.user_id, data.idempotency_key)
        if existing:
            if existing.project_id != self.project_id or existing.request_hash != request_hash:
                raise AlreadyExistsError(message="提交标识已用于其他任务，请重新提交")
            return existing
        if "knowledge_base_ids" not in data.model_fields_set:
            from uuid import UUID

            defaults = [UUID(v) for v in await projects.defaults(self.project_id)]
            data = data.model_copy(update={"knowledge_base_ids": defaults})
            request["knowledge_base_ids"] = [str(v) for v in defaults]
        config = resolve_generation_config(data.generation.model_dump())
        if data.mode == "knowledge_collaboration":
            if not data.knowledge_base_ids:
                raise BadRequestError(message="资料协作需要选择至少一个知识库")
            if data.tools:
                raise BadRequestError(message="资料协作仅访问所选知识库，请关闭额外工具")
            request["workflow_version"] = "knowledge-collaboration-v1"
        request["tools"] = await resolve_tools(
            user, [] if data.mode == "knowledge_collaboration" else data.tools
        )
        request["tool_policy_version"] = TOOL_POLICY_VERSION
        if data.knowledge_base_ids and PYTHON_TOOL in request["tools"]:
            raise BadRequestError(message="本版严格资料问答不执行代码，请创建不选知识库的计算任务")
        if data.input_file_ids and PYTHON_TOOL not in request["tools"]:
            raise BadRequestError(message="输入文件仅用于已授权的 Python 计算任务")
        if PYTHON_TOOL in request["tools"]:
            health = await sandbox_client.health()
            protocol = 2 if health.get("file_execution") else 1
            if data.input_file_ids and protocol != 2:
                raise BadRequestError(message="当前沙箱尚不支持文件执行")
            request["sandbox_protocol"] = protocol
            if data.input_file_ids:
                _, request["input_snapshot"] = await load_inputs(
                    self.db, self.user_id, data.input_file_ids
                )
        await KnowledgeService(self.db, self.user_id).validate_scope(
            data.knowledge_base_ids, None, require_ready=True
        )
        if data.retrieval_config is not None and not data.knowledge_base_ids:
            raise BadRequestError(message="检索参数需要与知识库一起使用")
        if data.knowledge_base_ids:
            retrieval = (
                data.retrieval_config
                or await KnowledgeService(self.db, self.user_id).get_retrieval_config()
            )
            request["retrieval_snapshot"] = capture(
                retrieval,
                override=data.retrieval_config is not None,
                collaboration=data.mode == "knowledge_collaboration",
            )
        if await self.repo.active_count(self.user_id) >= 5:
            raise RateLimitError(message="最多同时保留 5 个未结束任务，请先完成或取消已有任务")
        run = await self.repo.add(
            AgentRun(
                user_id=self.user_id,
                project_id=self.project_id,
                idempotency_key=data.idempotency_key,
                request_hash=request_hash,
                request=request,
                effective_config=config.model_dump(),
            )
        )
        await self.repo.event(run, "queued", {"message": "任务已排队"})
        return run

    async def cancel(self, run_id):
        run = await self.get(run_id, lock=True)
        if run.status in TERMINAL or run.status == "cancelling":
            return run
        if run.status == "running":
            run.status = "cancelling"
        else:
            run.status = "cancelled"
            run.pending_input = None
            run.finished_at = datetime.now(UTC)
        await self.repo.event(
            run,
            run.status,
            {"message": "正在停止执行" if run.status == "cancelling" else "任务已取消"},
        )
        return run

    async def resume(self, run_id, data):
        await self.repo.account_lock(self.user_id)
        run = await self.get(run_id, lock=True)
        from app.services.work_task import WorkTaskService

        await WorkTaskService(self.db, self.user_id, project_id=self.project_id).validate_run(run)
        payload = data.model_dump()
        if run.resume_input == payload:
            return run
        pending = run.pending_input
        if (
            run.status != "waiting_input"
            or not pending
            or pending["question_id"] != data.question_id
        ):
            raise AlreadyExistsError(message="问题已更新或任务已结束，请刷新任务")
        from app.services.clarification import answered_items, transcript, validate_answers

        validate_answers(pending, data.answers)
        run.resume_input = payload
        run.status = "queued"
        if pending.get("policy") or any(
            q.get("required") is not None for call in pending["calls"] for q in call["questions"]
        ):
            items = answered_items(pending, data.answers)
            if run.conversation_id:
                from app.db.models.conversation import Message

                assistant = await self.db.get(Message, run.assistant_message_id)
                if not assistant or assistant.conversation_id != run.conversation_id:
                    raise NotFoundError(message="会话消息已删除")
                # Keep this exchange inside its original turn so messages queued
                # while waiting can still recall the clarification and final answer.
                # The event below records the actual wall-clock reply time.
                replied_at = assistant.created_at
                self.db.add(
                    Message(
                        id=uuid5(run.id, "clarification:" + data.question_id),
                        conversation_id=run.conversation_id,
                        role="user",
                        content=transcript(items),
                        created_at=replied_at,
                    )
                )
                # The pending answer follows its clarification in transcript order.
                # The original user message and its requirement hash stay unchanged.
                assistant.created_at = replied_at + timedelta(microseconds=1)
            await self.repo.event(
                run,
                "clarification_answered",
                {
                    "message": "用户补充的信息已保存",
                    "question_id": data.question_id,
                    "items": items,
                },
            )
        await self.repo.event(run, "resumed", {"message": "补充信息已保存，等待继续执行"})
        return run
