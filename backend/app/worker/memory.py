"""Single bounded dispatcher alongside the existing task worker; durable PG queue."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, select, tuple_

from app.db.models.conversation import Message
from app.db.models.memory import MemoryExtractionJob, MemoryItem, MemoryProposal
from app.db.session import get_worker_db_context
from app.repositories.memory import MemoryRepository
from app.schemas.memory import MemoryCreate, MemoryUpdate
from app.services import memory_extraction as extraction
from app.services.mem0_memory import scope_key
from app.services.memory import MemoryService, content_hash, memory_state

logger = logging.getLogger(__name__)


async def current_job(db, job_id):
    job = await db.get(MemoryExtractionJob, job_id)
    if job is None:
        return None, None
    repo = MemoryRepository(db, job.user_id, job.project_id)
    await repo.lock_account()
    await db.refresh(job)
    return job, repo


async def consent(repo, job):
    pref = await repo.preference()
    return bool(
        pref and pref.enabled and pref.auto_extract and pref.revision == job.settings_revision
    )


def finish(job, status, error=None):
    job.status, job.error, job.finished_at = status, error, datetime.now(UTC)


async def newer_completed(db, repo, source):
    return await db.scalar(
        select(MemoryExtractionJob.id)
        .join(Message, Message.id == MemoryExtractionJob.source_message_id)
        .where(
            *repo.scope(MemoryExtractionJob),
            MemoryExtractionJob.status == "completed",
            tuple_(Message.created_at, Message.id) > (source.created_at, source.id),
        )
        .limit(1)
    )


async def execute(job_id, check_connection):
    async with get_worker_db_context() as db:
        job, repo = await current_job(db, job_id)
        if job is None or job.status not in ("queued", "running"):
            return
        if not await consent(repo, job):
            finish(job, "cancelled")
            return
        if job.attempts >= 2 or job.created_at < datetime.now(UTC) - timedelta(days=7):
            finish(job, "failed", "已达恢复次数或 7 天有效期，请在新消息中重新说明")
            return
        source = await repo.source(job.source_message_id)
        if source is None or source.role != "user" or not extraction.eligible(source.content):
            finish(job, "skipped")
            return
        if await newer_completed(db, repo, source):
            finish(job, "skipped", "已有更新的消息完成整理，不再回写旧信息")
            return
        targets = [i for i in await repo.list() if memory_state(i) == "active"]
        history = await extraction.context(db, repo, source)
        job.attempts += 1
        job.status, job.error, job.finished_at = "running", None, None
        attempt, text, config = job.attempts, source.content, job.configuration
    # No account/row transaction held over model calls.
    try:
        batch = await extraction.infer(
            text, history, targets, config, scope=scope_key(job.user_id, job.project_id)
        )
        await check_connection()
        async with get_worker_db_context() as db:
            job, repo = await current_job(db, job_id)
            if job is None or job.status != "running" or job.attempts != attempt:
                return
            if not await consent(repo, job):
                finish(job, "cancelled")
                return
            source = await repo.source(job.source_message_id)
            if source is None or source.role != "user" or source.content != text:
                finish(job, "cancelled")
                return
            if await newer_completed(db, repo, source):
                finish(job, "skipped", "已有更新的消息完成整理，不再回写旧信息")
                return
            count, hashes, changed_targets = 0, set(), set()
            service = MemoryService(db, job.user_id, project_id=job.project_id)
            project_count, account_count = await repo.counts()
            for candidate, target in extraction.validated_candidates(
                batch.result, text, batch.targets
            ):
                digest = content_hash(candidate.content)
                if digest in hashes or await repo.duplicate(digest, target.id if target else None):
                    continue
                if target:
                    current = await repo.get(target.id)
                    if (
                        current is None
                        or current.revision != target.revision
                        or memory_state(current) != "active"
                        or target.id in changed_targets
                    ):
                        continue
                elif project_count >= 100 or account_count >= 500:
                    job.error = "记忆数量已达上限，部分新信息未保存；可删除不再需要的记忆"
                    continue
                data = {
                    "title": candidate.title,
                    "content": candidate.content,
                    "kind": candidate.kind,
                    "pinned": target.pinned if target else False,
                    "expires_on": candidate.expires_on,
                    "source_message_id": source.id,
                }
                write = (
                    MemoryUpdate(**data, revision=target.revision)
                    if target
                    else MemoryCreate(**data)
                )
                await service.save(
                    write,
                    target.id if target else None,
                    source_override=True,
                    automatic_quote=candidate.quote,
                    vector=batch.vectors.get(candidate.content),
                )
                if target:
                    changed_targets.add(target.id)
                else:
                    project_count, account_count = project_count + 1, account_count + 1
                hashes.add(digest)
                count += 1
            job.result_count, job.usage = count, batch.usage
            finish(job, "completed", job.error)
    except Exception:
        # Never persist provider exceptions: they may include request text or credentials.
        async with get_worker_db_context() as db:
            job, repo = await current_job(db, job_id)
            if job and job.status == "running" and job.attempts == attempt:
                finish(
                    job,
                    "failed" if await consent(repo, job) else "cancelled",
                    "提取未完成，请检查模型配置后重试一次",
                )


async def index(item_id, check_connection):
    from app.services.memory_semantic import encode_note

    async with get_worker_db_context() as db:
        item = await db.get(MemoryItem, item_id)
        if item is None:
            return
        repo = MemoryRepository(db, item.user_id, item.project_id)
        await repo.lock_account()
        await db.refresh(item)
        pref = await repo.preference()
        if (
            not pref
            or not pref.enabled
            or not pref.semantic_recall
            or memory_state(item) != "active"
        ):
            return
        if item.embedding_revision == item.revision or item.index_attempts >= 2:
            return
        item.index_attempts += 1
        revision, settings_revision = item.revision, pref.revision
        title, content = item.title, item.content
    try:
        vector, model = await asyncio.to_thread(encode_note, title, content)
        await check_connection()
        async with get_worker_db_context() as db:
            repo = MemoryRepository(db, item.user_id, item.project_id)
            await repo.lock_account()
            current, pref = await repo.get(item_id), await repo.preference()
            if (
                current
                and current.revision == revision
                and memory_state(current) == "active"
                and pref
                and pref.enabled
                and pref.semantic_recall
                and pref.revision == settings_revision
            ):
                current.embedding, current.embedding_revision, current.embedding_model = (
                    vector,
                    revision,
                    model,
                )
    except Exception:
        logger.warning("Local memory index attempt failed")


async def locked(kind, item_id, action):
    from app.worker.agent_runs import connect

    # Two-int lock namespace is separate from task runs' bigint locks.
    lock_id = item_id
    if kind == 7301:
        from uuid import NAMESPACE_URL, uuid5

        async with get_worker_db_context() as db:
            job = await db.get(MemoryExtractionJob, item_id)
            if job is None:
                return False
            lock_id = uuid5(NAMESPACE_URL, scope_key(job.user_id, job.project_id))
    key = lock_id.int % (2**31 - 1)
    async with await connect() as conn:
        acquired = await (
            await conn.execute("SELECT pg_try_advisory_lock(%s, %s) AS acquired", (kind, key))
        ).fetchone()
        if not acquired["acquired"]:
            return False
        try:

            async def check_connection():
                await conn.execute("SELECT 1")

            await action(item_id, check_connection)
        finally:
            if not conn.closed:
                await conn.execute("SELECT pg_advisory_unlock(%s, %s)", (kind, key))
    return True


async def cycle():
    from app.db.models.memory import MemoryPreference

    async with get_worker_db_context() as db:
        jobs = list(
            await db.scalars(
                select(MemoryExtractionJob.id)
                .where(MemoryExtractionJob.status.in_(("queued", "running")))
                .order_by(MemoryExtractionJob.created_at)
                .limit(20)
            )
        )
        items = list(
            await db.scalars(
                select(MemoryItem.id)
                .join(
                    MemoryPreference,
                    (MemoryPreference.user_id == MemoryItem.user_id)
                    & MemoryPreference.project_id.is_not_distinct_from(MemoryItem.project_id),
                )
                .where(
                    MemoryPreference.enabled.is_(True),
                    MemoryPreference.semantic_recall.is_(True),
                    *MemoryRepository(db, None, None).active(),
                    MemoryItem.index_attempts < 2,
                    or_(
                        MemoryItem.embedding_revision.is_(None),
                        MemoryItem.embedding_revision != MemoryItem.revision,
                    ),
                )
                .order_by(MemoryItem.created_at)
                .limit(20)
            )
        )
        cutoff = datetime.now(UTC) - timedelta(days=30)
        await db.execute(delete(MemoryProposal).where(MemoryProposal.expires_at < cutoff))
        await db.execute(
            delete(MemoryExtractionJob).where(
                MemoryExtractionJob.finished_at < cutoff,
                MemoryExtractionJob.status.not_in(("queued", "running")),
            )
        )
    for job_id in jobs:
        if await locked(7301, job_id, execute):
            break
    for item_id in items:
        if await locked(7302, item_id, index):
            break


async def loop():
    while True:
        try:
            await cycle()
        except Exception:
            logger.warning("Memory dispatcher unavailable")
        await asyncio.sleep(3)
