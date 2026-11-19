"""Bounded file validation shared by task submission and remote result ingestion."""

import base64
import hashlib
import re
from pathlib import Path
from uuid import UUID

from app.core.exceptions import BadRequestError, ExternalServiceError, NotFoundError
from app.services.file_storage import get_file_storage
from app.services.file_upload import FileUploadService

INPUT_LIMIT = 5 * 1024**2
ARTIFACT_LIMIT = 2 * 1024**2
TOTAL_LIMIT = 4 * 1024**2
INPUT_TYPES = {"csv", "json", "txt", "md", "png", "jpg", "jpeg"}
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


def input_name(file_id, filename):
    suffix = Path(filename).suffix.lower().lstrip(".")
    safe = re.sub(r"[^\w .-]", "_", Path(filename).stem).replace("..", "_")[:60]
    return f"{UUID(str(file_id)).hex}_{safe}.{suffix}"


async def load_inputs(db, user_id, file_ids, snapshot=None):
    if len(file_ids) > 5 or len(set(file_ids)) != len(file_ids):
        raise BadRequestError(message="输入文件最多 5 个，不能重复")
    inputs, records, total = [], [], 0
    for file_id in file_ids:
        item = await FileUploadService(db).get_user_file(UUID(str(file_id)), user_id)
        suffix = Path(item.filename).suffix.lower().lstrip(".")
        if suffix not in INPUT_TYPES:
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
        name = input_name(item.id, item.filename)
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


async def load_execution_inputs(
    db, user_id, request, *, artifact_ids=(), work_context="", project_id=None
):
    """Mount explicitly selected task outputs, never arbitrary account artifacts.

    Check the checkpoint's business snapshot against live records, then verify bytes.
    Integrity checks say nothing about the factual correctness of the file content.
    """
    from app.services.run_artifact import RunArtifactService
    from app.services.work_task import WorkTaskService, context_data, context_matches

    file_ids = request.get("input_file_ids", [])
    selected = [str(value) for value in artifact_ids]
    if len(file_ids) + len(selected) > 5 or len(set(selected)) != len(selected):
        raise BadRequestError(message="输入文件最多 5 个，不能重复")
    if selected and request.get("sandbox_protocol", 1) != 2:
        raise BadRequestError(message="当前沙箱不支持文件计算")
    inputs, records = await load_inputs(db, user_id, file_ids, request.get("input_snapshot"))
    if not selected:
        return inputs, records
    if request.get("knowledge_base_ids") and request.get("knowledge_strict"):
        raise BadRequestError(message="严格资料模式不使用历史文件计算")
    snapshot = context_data(work_context)
    if not request.get("work_task") or not snapshot:
        raise NotFoundError(message="当前任务没有可复用的文件")
    current = await WorkTaskService(db, user_id, project_id=project_id).context(request)
    if not context_matches(work_context, current):
        raise BadRequestError(message="任务要求或历史文件已变化，请重新提交任务")
    available = {item["id"]: item for item in snapshot.get("artifacts", [])}
    service = RunArtifactService(db, user_id, project_id=project_id)
    total = sum(item["size"] for item in records)
    for artifact_id in selected:
        ref = available.get(artifact_id)
        if ref is None:
            raise NotFoundError(message="文件不在当前任务的可用产物中")
        item = await service.get(UUID(ref["run_id"]), UUID(artifact_id))
        suffix = Path(item.name).suffix.lower().lstrip(".")
        if suffix not in INPUT_TYPES:
            raise BadRequestError(message="计算输入支持 CSV、JSON、文本和 PNG/JPEG 图片")
        if not 0 <= item.size <= ARTIFACT_LIMIT:
            raise BadRequestError(message="历史文件大小无效")
        content = item.content
        digest = hashlib.sha256(content).hexdigest()
        if (
            len(content) != item.size
            or item.size != ref["size"]
            or item.name != ref["name"]
            or digest != item.sha256
            or digest != ref["sha256"]
        ):
            raise BadRequestError(message="历史文件完整性校验失败，请重新生成文件")
        total += len(content)
        if total > INPUT_LIMIT:
            raise BadRequestError(message="输入文件总大小不能超过 5 MiB")
        name = input_name(item.id, item.name)
        records.append(
            {
                "id": str(item.id),
                "run_id": str(item.run_id),
                "name": name,
                "size": len(content),
                "sha256": digest,
            }
        )
        inputs.append(
            {
                "name": name,
                "sha256": digest,
                "content_base64": base64.b64encode(content).decode("ascii"),
            }
        )
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
