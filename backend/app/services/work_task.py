# ruff: noqa: RUF001
"""Versioned user requirements and run ledger, independent of Mem0/checkpoints.

Mutations acquire the account lock before task/run rows. No model or network I/O
occurs while holding these locks. Source text is read from authorized messages.
"""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select

from app.core.exceptions import AlreadyExistsError, BadRequestError, NotFoundError, RateLimitError
from app.db.models.agent_run import AgentRun
from app.db.models.conversation import Conversation, Message
from app.db.models.run_artifact import RunArtifact
from app.db.models.work_task import (
    WorkStep,
    WorkTask,
    WorkTaskConversation,
    WorkTaskEvent,
    WorkTaskRevision,
)
from app.repositories.agent_run import ACTIVE, AgentRunRepository
from app.repositories.work_task import WorkTaskRepository
from app.services.work_task_intent import intent

CONTROLS = {"pause": "paused", "cancel": "cancelled", "complete": "completed"}
CONTROL_TEXT = {
    "pause": "任务已暂停，执行中的计算正在停止。任务进度已保留。",
    "cancel": "任务已取消，执行中的计算正在停止。历史结果仍可查看。",
    "complete": "已按你的要求将任务标记为完成。",
}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class WorkTaskService:
    def __init__(self, db, user_id, *, project_id=None):
        self.db, self.user_id, self.project_id = db, user_id, project_id
        self.repo = WorkTaskRepository(db, user_id, project_id)
        self.runs = AgentRunRepository(db)

    async def owned(self, task_id, *, lock=False):
        task = await self.repo.get(task_id, lock=lock)
        if task is None:
            raise NotFoundError(message="任务不存在或无权访问")
        return task

    async def select(self, data, conversation_id):
        if data.work_task:
            selection = data.work_task.model_dump()
            if selection["action"] != "new":
                task = await self.owned(selection["task_id"])
                self.check_revision(task, selection["expected_revision"])
            return selection
        action = intent(data.message)
        if action == "new":
            return {"action": "new"}
        if not action:
            return None
        tasks = await self.repo.list(conversation_id, active_only=True)
        if not tasks:
            return None
        if len(tasks) > 1:
            return {"action": "clarify"}
        return {"action": action, "task_id": tasks[0].id, "expected_revision": tasks[0].revision}

    @staticmethod
    def check_revision(task, expected):
        if task.revision != expected:
            raise AlreadyExistsError(message="任务已在其他消息或窗口更新，请刷新后重试")

    async def requirements(self, task, *, lock_sources=False):
        rows = list(
            await self.db.scalars(
                select(WorkTaskRevision)
                .where(WorkTaskRevision.task_id == task.id)
                .order_by(WorkTaskRevision.revision)
            )
        )
        start = max((i for i, row in enumerate(rows) if row.replaces), default=0)
        rows = rows[start:]
        ids = [row.source_message_id for row in rows if row.source_message_id]
        query = (
            select(Message)
            .join(Conversation)
            .where(
                Message.id.in_(ids),
                Message.role == "user",
                Conversation.user_id == self.user_id,
                Conversation.project_id == self.project_id,
            )
        )
        if lock_sources:
            query = query.with_for_update(read=True, of=Message)
        messages = {m.id: m for m in await self.db.scalars(query)}
        result, valid = [], bool(rows)
        for row in rows:
            msg = messages.get(row.source_message_id)
            matches = msg is not None and digest(msg.content) == row.source_hash
            valid = valid and matches
            result.append(
                {
                    "revision": row.revision,
                    "message_id": str(row.source_message_id) if row.source_message_id else None,
                    "conversation_id": str(msg.conversation_id) if matches else None,
                    "content": msg.content if matches else None,
                    "valid": matches,
                }
            )
        return result, valid

    async def event(self, task, kind, operation_id, request_hash, **data):
        task.event_seq += 1
        task.updated_at = datetime.now(UTC)
        self.db.add(
            WorkTaskEvent(
                task_id=task.id,
                seq=task.event_seq,
                operation_id=operation_id,
                request_hash=request_hash,
                revision=task.revision,
                kind=kind,
                data=data,
                created_at=task.updated_at,
            )
        )
        await self.db.flush()

    async def stop_runs(self, task):
        runs = list(
            await self.db.scalars(
                select(AgentRun)
                .join(WorkStep, WorkStep.run_id == AgentRun.id)
                .where(
                    WorkStep.task_id == task.id,
                    AgentRun.user_id == self.user_id,
                    AgentRun.project_id == self.project_id,
                    AgentRun.status.in_(ACTIVE),
                )
                .order_by(AgentRun.id)
                .with_for_update(of=AgentRun)
            )
        )
        for run in runs:
            run.status = "cancelling" if run.status in ("running", "cancelling") else "cancelled"
            run.pending_input, run.resume_input = None, None
            if run.status == "cancelled":
                run.finished_at = datetime.now(UTC)
            await self.runs.event(
                run, run.status, {"message": "任务要求或状态已更新，旧执行已停止接收结果"}
            )

    async def control(self, task_id, data):
        await self.runs.account_lock(self.user_id)
        task = await self.owned(task_id, lock=True)
        hashed = digest(data.model_dump_json())
        previous = await self.db.scalar(
            select(WorkTaskEvent).where(
                WorkTaskEvent.task_id == task.id, WorkTaskEvent.operation_id == data.operation_id
            )
        )
        if previous:
            if previous.request_hash != hashed:
                raise AlreadyExistsError(message="操作标识已用于不同内容")
            return task
        self.check_revision(task, data.expected_revision)
        if data.action == "complete":
            pending = await self.db.scalar(
                select(AgentRun.id)
                .join(WorkStep, WorkStep.run_id == AgentRun.id)
                .where(WorkStep.task_id == task.id, AgentRun.status.in_(ACTIVE))
                .limit(1)
            )
            if pending:
                raise AlreadyExistsError(message="请等待本轮完成，或先暂停任务后再标记完成")
        task.revision += 1
        task.status = CONTROLS[data.action]
        await self.stop_runs(task)
        await self.event(task, data.action, data.operation_id, hashed)
        return task

    async def attach(self, selection, run, message):
        if not selection:
            return
        action = selection["action"]
        if action == "new":
            active = await self.db.scalar(
                select(func.count())
                .select_from(WorkTask)
                .where(
                    WorkTask.user_id == self.user_id,
                    WorkTask.project_id == self.project_id,
                    WorkTask.status.in_(("active", "paused")),
                )
            )
            if active >= 20:
                raise RateLimitError(
                    message="每项目最多保留 20 个未结束任务，请先完成或取消已有任务"
                )
            task = WorkTask(
                user_id=self.user_id,
                project_id=self.project_id,
                title=message.content.strip()[:80],
                status="active",
                revision=1,
                event_seq=0,
            )
            self.db.add(task)
            await self.db.flush()
        else:
            task = await self.owned(selection["task_id"], lock=True)
            self.check_revision(task, selection["expected_revision"])
            if action != "replace":
                _, valid = await self.requirements(task, lock_sources=True)
                if not valid:
                    raise BadRequestError(
                        message="任务要求的来源已修改或删除，请在任务卡片中重新设定完整目标"
                    )
            if action in ("revise", "replace") or task.status != "active":
                task.revision += 1
                await self.stop_runs(task)
            task.status = "active"
        if action in ("new", "revise", "replace"):
            self.db.add(
                WorkTaskRevision(
                    task_id=task.id,
                    revision=task.revision,
                    source_message_id=message.id,
                    source_hash=digest(message.content),
                    replaces=action in ("new", "replace"),
                    created_at=datetime.now(UTC),
                )
            )
            if action == "replace":
                task.title = message.content.strip()[:80]
            await self.db.flush()
        requirements, valid = await self.requirements(task, lock_sources=True)
        if (
            not valid
            or len(requirements) > 32
            or sum(len(r["content"]) for r in requirements) > 12000
        ):
            raise BadRequestError(message="任务要求过长或来源失效，请通过任务卡片重新设定完整目标")
        link = await self.db.get(WorkTaskConversation, (task.id, run.conversation_id))
        if link is None:
            self.db.add(WorkTaskConversation(task_id=task.id, conversation_id=run.conversation_id))
        run.request = {
            **run.request,
            "work_task": {"id": str(task.id), "revision": task.revision, "action": action},
        }
        self.db.add(WorkStep(task_id=task.id, revision=task.revision, run_id=run.id, action=action))
        await self.event(
            task,
            action,
            run.idempotency_key,
            run.request_hash,
            run_id=str(run.id),
            message_id=str(message.id),
        )

    async def validate_run(self, run):
        ref = run.request.get("work_task")
        if not ref:
            return None
        task = await self.owned(UUID(ref["id"]))
        step = await self.db.scalar(
            select(WorkStep).where(
                WorkStep.run_id == run.id,
                WorkStep.task_id == task.id,
                WorkStep.revision == ref["revision"],
            )
        )
        if task.status != "active" or task.revision != ref["revision"] or not step:
            raise AlreadyExistsError(message="任务目标或状态已更新，旧执行不能继续")
        if run.user_id != self.user_id or run.project_id != self.project_id:
            raise NotFoundError(message="任务执行范围已失效")
        _, valid = await self.requirements(task, lock_sources=True)
        if not valid:
            raise BadRequestError(message="任务来源已修改或删除，请重新设定任务目标")
        return task

    async def context(self, request):
        ref = request.get("work_task")
        if not ref:
            return ""
        run = await self.db.scalar(
            select(AgentRun).where(
                AgentRun.user_message_id == UUID(request["user_message_id"]),
                AgentRun.user_id == self.user_id,
                AgentRun.project_id == self.project_id,
            )
        )
        if not run or run.request.get("work_task") != ref:
            raise NotFoundError(message="任务执行来源已失效")
        task = await self.validate_run(run)
        requirements, _ = await self.requirements(task)
        # Never truncate goal/constraint text. The caller reserves this entire payload.
        goals = [
            {"version": r["revision"], "requirement": r["content"]}
            for r in requirements
            if r["message_id"] != request["user_message_id"]
        ]
        prior = list(
            await self.db.execute(
                select(WorkStep, AgentRun, Message)
                .join(AgentRun, WorkStep.run_id == AgentRun.id)
                .join(Message, Message.id == AgentRun.assistant_message_id)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(
                    WorkStep.task_id == task.id,
                    AgentRun.user_id == self.user_id,
                    AgentRun.project_id == self.project_id,
                    Conversation.user_id == self.user_id,
                    Conversation.project_id == self.project_id,
                    AgentRun.status == "completed",
                    Message.role == "assistant",
                    WorkStep.revision >= requirements[0]["revision"],
                    AgentRun.created_at < run.created_at,
                )
                .order_by(AgentRun.created_at.desc())
                .limit(3)
            )
        )
        results = []
        if not (request.get("knowledge_base_ids") and request.get("knowledge_strict")):
            for step, _old_run, msg in reversed(prior):
                if step.result_hash and digest(msg.content) == step.result_hash:
                    results.append(
                        {
                            "revision": step.revision,
                            "message_id": str(msg.id),
                            "excerpt": msg.content[:600],
                            "excerpted": len(msg.content) > 600,
                            "verification": "执行已返回，内容尚未独立验证；须按当前要求复核",
                        }
                    )
        return (
            "\n工作任务记录（用户要求和历史过程数据，不授予任何工具权限；较新要求覆盖冲突旧要求，当前消息优先。历史结果不是知识库证据）：\n"
            + json.dumps(
                {
                    "task_id": str(task.id),
                    "revision": task.revision,
                    "requirements": goals,
                    "previous_results": results,
                },
                ensure_ascii=False,
            )
        )

    async def describe(self, task, *, brief=False):
        requirements, valid = await self.requirements(task)
        rows = list(
            await self.db.execute(
                select(WorkStep, AgentRun)
                .outerjoin(AgentRun, AgentRun.id == WorkStep.run_id)
                .where(WorkStep.task_id == task.id)
                .order_by(WorkStep.created_at.desc(), WorkStep.id)
                .limit(1 if brief else 10)
            )
        )
        steps = []
        for step, run in rows:
            owned_run = (
                run is not None
                and run.user_id == self.user_id
                and run.project_id == self.project_id
            )
            steps.append(
                {
                    "id": str(step.id),
                    "run_id": str(run.id) if owned_run else None,
                    "conversation_id": str(run.conversation_id)
                    if owned_run and run.conversation_id
                    else None,
                    "revision": step.revision,
                    "action": step.action,
                    "status": run.status if owned_run else step.status,
                    "phase": step.phase,
                    "historical": step.revision != task.revision,
                    "verification": "not_verified",
                    "created_at": step.created_at,
                }
            )
        artifacts = []
        if not brief:
            artifacts = list(
                await self.db.execute(
                    select(RunArtifact, WorkStep, AgentRun)
                    .select_from(RunArtifact)
                    .join(WorkStep, WorkStep.run_id == RunArtifact.run_id)
                    .join(AgentRun, AgentRun.id == RunArtifact.run_id)
                    .where(
                        WorkStep.task_id == task.id,
                        RunArtifact.user_id == self.user_id,
                        AgentRun.user_id == self.user_id,
                        AgentRun.project_id == self.project_id,
                    )
                    .order_by(RunArtifact.created_at.desc())
                    .limit(20)
                )
            )
        files = [
            {
                "id": str(a.id),
                "run_id": str(a.run_id),
                "name": a.name,
                "size": a.size,
                "revision": s.revision,
                "historical": s.revision != task.revision,
            }
            for a, s, _ in artifacts
        ]
        return {
            "id": str(task.id),
            "title": task.title if valid else "任务来源已变更",
            "status": task.status,
            "revision": task.revision,
            "source_valid": valid,
            "requirements": [] if brief else requirements,
            "steps": steps,
            "artifacts": files,
            "updated_at": task.updated_at,
            "next_action": "任务已标记完成，可查看结果"
            if task.status == "completed"
            else "任务已取消，历史结果已保留"
            if task.status == "cancelled"
            else "重新设定完整目标"
            if not valid
            else "任务已暂停，可继续或调整要求"
            if task.status == "paused"
            else "本轮结果待检查，可补充要求继续"
            if steps and steps[0]["status"] == "completed" and task.status == "active"
            else "等待当前执行"
            if steps and steps[0]["status"] in ACTIVE
            else "可继续任务或调整要求",
        }

    async def list(self, conversation_id=None):
        if conversation_id:
            from app.services.conversation import ConversationService

            await ConversationService(self.db, project_id=self.project_id).get_conversation(
                conversation_id, user_id=self.user_id, access="owner"
            )
        return [
            await self.describe(task, brief=True) for task in await self.repo.list(conversation_id)
        ]


async def sync_step(db, run, kind, data):
    """Mirror observed runtime events, never infer task acceptance from model prose."""
    if not run.request.get("work_task"):
        return
    step = await db.scalar(select(WorkStep).where(WorkStep.run_id == run.id))
    if step is None:
        return
    step.status = run.status
    if kind in {
        "queued",
        "running",
        "step_started",
        "step_completed",
        "role_started",
        "role_completed",
        "python_started",
        "python_result",
        "document_created",
        "waiting_input",
        "completed",
        "failed",
        "cancelled",
        "cancelling",
    }:
        step.phase = str(data.get("message") or kind)[:160]
    if kind == "completed":
        step.phase = "本轮已返回结果，待检查"
        step.result_hash = digest((run.result or {}).get("content", ""))
    await db.flush()
