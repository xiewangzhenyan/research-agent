"""Opt-in automatic memory queue and source validation for the Mem0 engine."""

import re
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.db.models.conversation import Message
from app.db.models.memory import MemoryExtractionJob
from app.repositories.memory import MemoryRepository
from app.services.model_config import allowed_models, resolve_generation_config

# Conservative exclusion, not a complete secret detector; source checks also apply.
SECRET = re.compile(
    r"(?i)(password|passwd|api[_ -]?key|secret|access[_ -]?token|密码|密钥|口令|BEGIN .{0,15}PRIVATE KEY|sk-[a-z0-9]{12,}|bearer\s+[a-z0-9._-]+)"
)


def eligible(text):
    return isinstance(text, str) and 4 <= len(text.strip()) <= 6000 and not SECRET.search(text)


async def enqueue(db, user_id, project_id, source, *, strict_knowledge=False):
    if strict_knowledge or not eligible(source.content) or source.role != "user":
        return
    repo = MemoryRepository(db, user_id, project_id)
    pref = await repo.preference()
    if pref is None or pref.enabled is not True or pref.auto_extract is not True:
        return
    await repo.lock_account()
    pref = await repo.preference()
    if pref is None or not pref.enabled or not pref.auto_extract:
        return
    if await db.scalar(
        select(MemoryExtractionJob.id).where(MemoryExtractionJob.source_message_id == source.id)
    ):
        return
    outstanding = await db.scalar(
        select(func.count())
        .select_from(MemoryExtractionJob)
        .where(
            MemoryExtractionJob.user_id == user_id,
            MemoryExtractionJob.status.in_(("queued", "running")),
        )
    )
    if outstanding >= 10 or await repo.daily_jobs() >= 20:
        return
    # A removed deployment model must never make persisting a chat fail.
    if pref.extraction_model and pref.extraction_model not in allowed_models():
        return
    config = resolve_generation_config({"model": pref.extraction_model, "thinking_effort": "off"})
    await repo.save(
        MemoryExtractionJob(
            user_id=user_id,
            project_id=project_id,
            source_message_id=source.id,
            settings_revision=pref.revision,
            configuration=config.model_dump(),
        )
    )


async def context(db, repo, source):
    rows = list(
        await db.scalars(
            select(Message)
            .where(
                Message.conversation_id == source.conversation_id,
                Message.role == "user",
                Message.created_at < source.created_at,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(6)
        )
    )
    history, remaining = [], 3000
    for row in rows:
        if eligible(row.content) and remaining:
            history.append(row.content[: min(1000, remaining)])
            remaining -= len(history[-1])
    return list(reversed(history))


async def infer(source, history, targets, configuration, *, scope):
    from app.services.mem0_memory import extract

    return await extract(source, history, targets, configuration, scope=scope)


def validated_candidates(result, source, targets):
    for candidate in result.memories:
        if (
            not candidate.title.strip()
            or not candidate.content.strip()
            or SECRET.search(candidate.content)
        ):
            continue
        if candidate.quote not in source:
            continue
        if candidate.expires_on and (
            not candidate.expiry_quote
            or candidate.expiry_quote not in source
            or candidate.expires_on < datetime.now(UTC).date()
        ):
            continue
        if candidate.action == "update":
            if candidate.target is None or candidate.target >= len(targets):
                continue
            target = targets[candidate.target]
        else:
            if candidate.target is not None:
                continue
            target = None
        yield candidate, target
