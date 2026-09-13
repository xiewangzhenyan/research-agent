"""Project memory lifecycle. Models suggest; authenticated users approve changes."""

import hashlib
from datetime import UTC, datetime

from app.core.config import settings
from app.core.exceptions import AlreadyExistsError, BadRequestError, NotFoundError, RateLimitError
from app.db.models.memory import MemoryExtractionJob, MemoryItem, MemoryPreference
from app.repositories.memory import MemoryRepository
from app.schemas.memory import MemoryCreate, MemoryResponse, MemoryUpdate
from app.services.memory_recall import select_memories
from app.services.model_config import allowed_models, resolve_generation_config
from app.services.project import ProjectService


def content_hash(content):
    return hashlib.sha256(" ".join(content.split()).encode()).hexdigest()


def memory_state(item):
    if item.archived_at:
        return "archived"
    if item.expires_on and item.expires_on < datetime.now(UTC).date():
        return "expired"
    return "active"


def public_item(item):
    data = MemoryResponse.model_validate(item)
    data.state = memory_state(item)
    data.index_status = (
        "ready"
        if item.embedding_revision == item.revision
        else "failed"
        if item.index_attempts >= 2
        else "pending"
    )
    return data


class MemoryService:
    def __init__(self, db, user_id, *, project_id=None):
        self.db, self.user_id, self.project_id = db, user_id, project_id
        self.repo = MemoryRepository(db, user_id, project_id)

    async def authorize(self):
        await ProjectService(self.db, self.user_id).validate(self.project_id)

    async def settings(self):
        await self.authorize()
        pref = await self.repo.preference()
        return {
            "enabled": pref.enabled if pref else False,
            "revision": pref.revision if pref else 0,
            "auto_extract": pref.auto_extract if pref else False,
            "semantic_recall": pref.semantic_recall if pref else True,
            "extraction_model": (pref.extraction_model if pref else None) or settings.AI_MODEL,
        }

    async def configure(self, data):
        await self.authorize()
        await self.repo.lock_account()
        pref = await self.repo.preference()
        if data.revision != (pref.revision if pref else 0):
            raise AlreadyExistsError(message="记忆设置已更新，请刷新后重试")
        if data.extraction_model is not None and data.extraction_model not in allowed_models():
            raise BadRequestError(message="请选择已配置的提取模型")
        if pref is None:
            pref = MemoryPreference(
                user_id=self.user_id,
                project_id=self.project_id,
                revision=0,
                auto_extract=False,
                semantic_recall=True,
            )
        pref.enabled = data.enabled
        for key in ("auto_extract", "semantic_recall", "extraction_model"):
            if getattr(data, key) is not None:
                setattr(pref, key, getattr(data, key))
        if not pref.enabled:
            pref.auto_extract = False
        pref.revision += 1
        await self.repo.save(pref)
        # In-flight jobs recheck this revision before writing candidates.
        return await self.settings()

    async def list(self):
        config = await self.settings()
        proposals = await self.repo.proposals()
        items = await self.repo.list()
        by_id = {i.id: i for i in items}
        return {
            **config,
            "items": [public_item(item) for item in items],
            "limit": 100,
            "proposals": [
                {
                    "id": str(p.id),
                    "revision": p.revision,
                    "action": p.action,
                    "payload": p.payload,
                    "reason": p.reason,
                    "quote": p.quote,
                    "source_message_id": str(p.source_message_id),
                    "target_id": str(p.target_id) if p.target_id else None,
                    "target_revision": p.target_revision,
                    "target": public_item(by_id[p.target_id]) if p.target_id in by_id else None,
                    "expires_at": p.expires_at,
                }
                for p in proposals
            ],
            "jobs": [
                {
                    "id": str(j.id),
                    "status": j.status,
                    "attempts": j.attempts,
                    "error": j.error,
                    "result_count": j.result_count,
                    "created_at": j.created_at,
                    "model": j.configuration.get("model"),
                    "usage": j.usage,
                }
                for j in await self.repo.jobs()
            ],
            "daily_jobs": await self.repo.daily_jobs(),
            "daily_limit": 20,
        }

    async def get(self, item_id):
        await self.authorize()
        item = await self.repo.get(item_id)
        if item is None:
            raise NotFoundError(message="当前项目中不存在此记忆")
        return item

    async def save(self, data, item_id=None, *, source_override=False):
        await self.authorize()
        await self.repo.lock_account()
        item = await self.get(item_id) if item_id else None
        if item is not None and item.revision != data.revision:
            raise AlreadyExistsError(message="这条记忆已被修改，请刷新后重新编辑")
        if data.source_message_id and not await self.repo.source(data.source_message_id):
            raise NotFoundError(message="来源消息不存在或不属于当前项目")
        if (
            item is not None
            and data.source_message_id != item.source_message_id
            and not source_override
        ):
            raise AlreadyExistsError(message="编辑记忆时不能更换来源")
        digest = content_hash(data.content)
        if await self.repo.duplicate(digest, item_id):
            raise AlreadyExistsError(message="当前项目已保存相同内容，请编辑或恢复已有记忆")
        if item is None:
            project_count, account_count = await self.repo.counts()
            if project_count >= 100 or account_count >= 500:
                raise RateLimitError(
                    message="记忆数量已达上限(每项目 100 条、每账号 500 条)，请整理后添加"
                )
            item = MemoryItem(user_id=self.user_id, project_id=self.project_id, revision=0)
        else:
            await self.repo.snapshot(item)
        for key in ("title", "content", "kind", "pinned", "source_message_id", "expires_on"):
            setattr(item, key, getattr(data, key))
        item.content_hash = digest
        item.revision += 1
        item.embedding, item.embedding_revision, item.embedding_model, item.index_attempts = (
            None,
            None,
            None,
            0,
        )
        await self.repo.save(item)
        await self.repo.snapshot(item)
        return public_item(item)

    async def archive(self, item_id, revision, archived):
        await self.authorize()
        await self.repo.lock_account()
        item = await self.get(item_id)
        if item.revision != revision:
            raise AlreadyExistsError(message="记忆已变化，请刷新后操作")
        await self.repo.snapshot(item)
        item.archived_at = datetime.now(UTC) if archived else None
        item.revision += 1
        item.embedding_revision, item.index_attempts = None, 0
        await self.repo.save(item)
        await self.repo.snapshot(item)
        return public_item(item)

    async def history(self, item_id):
        await self.get(item_id)
        return {
            "items": [
                {"revision": v.revision, "snapshot": v.snapshot, "created_at": v.created_at}
                for v in await self.repo.versions(item_id)
            ],
            "limit": 30,
        }

    async def delete(self, item_id, revision):
        await self.authorize()
        await self.repo.lock_account()
        item = await self.get(item_id)
        if item.revision != revision:
            raise AlreadyExistsError(message="这条记忆已更新，请刷新后再删除")
        await self.repo.delete(item)

    async def source(self, item_id):
        item = await self.get(item_id)
        message = await self.repo.source(item.source_message_id) if item.source_message_id else None
        if message is None:
            raise NotFoundError(message="原始消息已删除或不可访问")
        return {"conversation_id": str(message.conversation_id)}

    async def decide(self, proposal_id, revision, data=None):
        await self.authorize()
        await self.repo.lock_account()
        proposal = await self.repo.proposal(proposal_id)
        if proposal is None:
            raise NotFoundError(message="当前项目中不存在此建议")
        if (
            proposal.revision != revision
            or proposal.status != "pending"
            or proposal.expires_at <= datetime.now(UTC)
        ):
            raise AlreadyExistsError(message="建议已处理或超过 7 天有效期，请刷新")
        saved = None
        if data is not None:
            if data.source_message_id != proposal.source_message_id:
                raise BadRequestError(message="不能更换建议的来源消息")
            if proposal.target_id:
                target = await self.get(proposal.target_id)
                if target.revision != proposal.target_revision or memory_state(target) != "active":
                    raise AlreadyExistsError(
                        message="原记忆已变化或已失效，请先核对原记忆；此建议未覆盖任何内容"
                    )
                write = MemoryUpdate(
                    **data.model_dump(exclude={"revision"}), revision=proposal.target_revision
                )
                saved = await self.save(write, target.id, source_override=True)
            else:
                saved = await self.save(MemoryCreate(**data.model_dump(exclude={"revision"})))
            proposal.status = "accepted"
        else:
            proposal.status = "rejected"
        proposal.revision += 1
        await self.repo.save(proposal)
        return {"status": proposal.status, "item": saved}

    async def retry(self, job_id):
        await self.authorize()
        await self.repo.lock_account()
        from sqlalchemy import select

        job = await self.db.scalar(
            select(MemoryExtractionJob).where(
                *self.repo.scope(MemoryExtractionJob), MemoryExtractionJob.id == job_id
            )
        )
        if job is None:
            raise NotFoundError(message="任务不存在")
        config = await self.settings()
        if not config["enabled"] or not config["auto_extract"]:
            raise BadRequestError(message="请先开启自动整理候选")
        if job.status != "failed" or job.attempts >= 2:
            raise AlreadyExistsError(message="任务已重试或不处于失败状态")
        from sqlalchemy import func

        outstanding = await self.db.scalar(
            select(func.count())
            .select_from(MemoryExtractionJob)
            .where(
                MemoryExtractionJob.user_id == self.user_id,
                MemoryExtractionJob.status.in_(("queued", "running")),
            )
        )
        if outstanding >= 10:
            raise RateLimitError(message="账号已有 10 个记忆任务等待处理，请稍后重试")
        job.status, job.error, job.settings_revision = "queued", None, config["revision"]
        job.configuration = resolve_generation_config(
            {"model": config["extraction_model"], "thinking_effort": "off"}
        ).model_dump()
        await self.repo.save(job)
        return {"status": "queued"}

    async def reindex(self):
        await self.authorize()
        await self.repo.lock_account()
        for item in await self.repo.list():
            if memory_state(item) == "active":
                (
                    item.embedding,
                    item.embedding_revision,
                    item.embedding_model,
                    item.index_attempts,
                ) = None, None, None, 0
        await self.db.flush()
        return {"status": "queued"}

    async def recall(self, query, *, strict_knowledge=False):
        if strict_knowledge:
            return {"status": "strict_knowledge", "items": [], "omitted": 0, "estimated_tokens": 0}
        config = await self.settings()
        if not config["enabled"]:
            return {"status": "disabled", "items": [], "omitted": 0, "estimated_tokens": 0}
        items = [i for i in await self.repo.list() if memory_state(i) == "active"]
        scores, semantic_status = {}, "off"
        if config["semantic_recall"]:
            indexed = [i for i in items if i.embedding_revision == i.revision]
            semantic_status = "pending" if items and not indexed else "empty"
            if indexed:
                from app.services.memory_semantic import query_vector

                try:
                    vector, fingerprint = await query_vector(query)
                except Exception:
                    semantic_status = "unavailable"
                else:
                    if any(i.embedding_model == fingerprint for i in indexed):
                        scores = await self.repo.semantic(vector, fingerprint)
                        semantic_status = "ready"
                    else:
                        semantic_status = "model_changed"
        result = select_memories(query, items, semantic_scores=scores)
        return {
            **result,
            "retrieval_mode": "hybrid" if semantic_status == "ready" else "keyword",
            "semantic_status": semantic_status,
        }
