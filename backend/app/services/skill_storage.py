"""Content-addressed, account-scoped skill blobs; no uploaded paths on disk."""

import asyncio
import hashlib
from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.core.exceptions import RateLimitError
from app.services.file_storage import LocalFileStorage


class SkillStorage(LocalFileStorage):
    async def save(self, user_id, filename, data):
        owner = str(UUID(user_id))
        digest = hashlib.sha256(data).hexdigest()
        key = f"{owner}/{digest}"
        path = self._resolve_safe_path(key)

        def write():
            path.parent.mkdir(parents=True, exist_ok=True)
            if (
                not path.exists()
                and sum(p.stat().st_size for p in path.parent.iterdir() if p.is_file()) + len(data)
                > 200 * 1024 * 1024
            ):
                raise RateLimitError(
                    message="技能文件已达到账号 200 MiB 配额，请联系管理员回收历史文件"
                )
            # A partial write is detected by digest verification and repaired below.
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                temporary = path.with_suffix(".tmp")
                temporary.write_bytes(data)
                temporary.replace(path)

        await asyncio.to_thread(write)
        return key


def get_skill_storage():
    return SkillStorage(Path(settings.MEDIA_DIR) / "skills")
