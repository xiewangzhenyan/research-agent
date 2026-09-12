# ruff: noqa: RUF001
"""Bounded file validation shared by task submission and remote result ingestion."""

import base64
import hashlib
import re
from pathlib import Path
from uuid import UUID

from app.core.exceptions import BadRequestError, ExternalServiceError
from app.services.file_storage import get_file_storage
from app.services.file_upload import FileUploadService

INPUT_LIMIT = 5 * 1024**2
ARTIFACT_LIMIT = 2 * 1024**2
TOTAL_LIMIT = 4 * 1024**2
TYPES = {
    "csv": "text/csv",
    "json": "application/json",
    "txt": "text/plain",
    "md": "text/markdown",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "pdf": "application/pdf",
}


async def load_inputs(db, user_id, file_ids, snapshot=None):
    if len(file_ids) > 5 or len(set(file_ids)) != len(file_ids):
        raise BadRequestError(message="输入文件最多 5 个，不能重复")
    inputs, records, total = [], [], 0
    for file_id in file_ids:
        item = await FileUploadService(db).get_user_file(UUID(str(file_id)), user_id)
        suffix = Path(item.filename).suffix.lower().lstrip(".")
        if suffix not in {"csv", "json", "txt", "md", "png", "jpg", "jpeg"}:
            raise BadRequestError(message="计算输入支持 CSV、JSON、文本和 PNG/JPEG 图片")
        if not 0 <= item.size <= INPUT_LIMIT:
            raise BadRequestError(message="输入文件总大小不能超过 5 MiB")
        path = get_file_storage().get_full_path(item.storage_path)
        if path is None:
            raise BadRequestError(message="输入文件已失效，请重新上传")
        # Local storage is the current backend. Bounded read even if metadata is stale.
        try:
            with path.open("rb") as stream:
                content = stream.read(INPUT_LIMIT + 1)
        except OSError as exc:
            raise BadRequestError(message="输入文件无法读取") from exc
        total += len(content)
        if total > INPUT_LIMIT or len(content) != item.size:
            raise BadRequestError(message="输入文件已变化或超过 5 MiB 限额")
        safe = re.sub(r"[^\w .-]", "_", Path(item.filename).stem).replace("..", "_")[:60]
        name = f"{item.id.hex}_{safe}.{suffix}"
        digest = hashlib.sha256(content).hexdigest()
        records.append({"id": str(item.id), "name": name, "size": len(content), "sha256": digest})
        inputs.append(
            {
                "name": name,
                "sha256": digest,
                "content_base64": base64.b64encode(content).decode("ascii"),
            }
        )
    if snapshot is not None and snapshot != records:
        raise BadRequestError(message="任务输入文件已变化，请重新提交任务")
    return inputs, records


def validate_artifacts(items, state):
    try:
        if not isinstance(items, list) or len(items) > 10 or (state != "completed" and items):
            raise ValueError("Invalid bundle")
        output, names, total = [], set(), 0
        for item in items:
            name = item["name"]
            if (
                not isinstance(name, str)
                or not re.fullmatch(r"[\w][\w .-]{0,119}", name)
                or ".." in name
                or name in names
            ):
                raise ValueError("Invalid name")
            suffix = name.rsplit(".", 1)[-1].lower()
            if suffix not in TYPES or item["mime_type"] != TYPES[suffix]:
                raise ValueError("Invalid media type")
            encoded = item["content_base64"]
            if not isinstance(encoded, str) or len(encoded) > 3 * 1024**2:
                raise ValueError("Invalid payload")
            content = base64.b64decode(encoded, validate=True)
            total += len(content)
            if (
                len(content) > ARTIFACT_LIMIT
                or total > TOTAL_LIMIT
                or type(item["size"]) is not int
                or item["size"] != len(content)
                or item["sha256"] != hashlib.sha256(content).hexdigest()
            ):
                raise ValueError("Invalid size or digest")
            names.add(name)
            output.append(
                {
                    "name": name,
                    "mime_type": TYPES[suffix],
                    "size": len(content),
                    "sha256": item["sha256"],
                    "content": content,
                }
            )
        return output
    except (KeyError, TypeError, ValueError) as exc:
        raise ExternalServiceError(message="沙箱产物校验失败，未保存文件") from exc
