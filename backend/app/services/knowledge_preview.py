"""Ephemeral, bounded parsing previews and file/account-bound confirmation receipts."""

import asyncio
import fcntl
import hashlib
import json
import os
import sys
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.schemas.knowledge import ChunkingConfig

# Increment when the parsing/chunking contract changes; old receipts must be re-previewed.
PREVIEW_VERSION = "native-preview-v1"
PREVIEW_TIMEOUT = 25
PREVIEW_ITEMS = 80


def validate_file(filename, data):
    from app.services.knowledge import ALLOWED_EXTENSIONS, MAX_DOCUMENT_BYTES

    filename = Path(filename.replace("\\", "/")).name[:255]
    if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise BadRequestError(message="支持 PDF、Word (.docx)、TXT、Markdown 和 CSV")
    if not data or len(data) > MAX_DOCUMENT_BYTES:
        raise BadRequestError(message="文件不能为空，且不能超过 10 MB")
    return filename


def issue_receipt(user_id, base_id, filename, data, config):
    return jwt.encode(
        {
            "type": "knowledge_preview",
            "sub": str(user_id),
            "base": str(base_id),
            "filename": filename,
            "sha256": hashlib.sha256(data).hexdigest(),
            "config": config.model_dump(),
            "version": PREVIEW_VERSION,
            "exp": datetime.now(UTC) + timedelta(minutes=15),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def verify_receipt(token, user_id, base_id, filename, data):
    try:
        claims = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        expected = {
            "type": "knowledge_preview",
            "sub": str(user_id),
            "base": str(base_id),
            "filename": filename,
            "sha256": hashlib.sha256(data).hexdigest(),
            "version": PREVIEW_VERSION,
        }
        if any(claims.get(k) != v for k, v in expected.items()):
            raise ValueError("mismatched preview")
        return ChunkingConfig.model_validate(claims["config"])
    except (jwt.PyJWTError, ValueError, KeyError, ValidationError) as exc:
        raise BadRequestError(message="预览已失效或文件已变更，请重新生成预览") from exc


async def run_preview(data: bytes, filename: str, config: ChunkingConfig):
    # Non-blocking file lock covers all API workers in this container. No waiting queue,
    # stored source files, vectors or DB records; child is killed on timeout/cancellation.
    with open("/tmp/agent-knowledge-preview.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BadRequestError(message="预览服务忙，请稍后重试") from exc
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "app.services.knowledge_preview_worker",
                filename,
                str(config.chunk_size),
                str(config.chunk_overlap),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"},
            )
            try:
                output, _ = await asyncio.wait_for(process.communicate(data), PREVIEW_TIMEOUT)
            except TimeoutError as exc:
                raise BadRequestError(message="预览超时，请拆分文件后重试") from exc
            if process.returncode != 0:
                raise BadRequestError(message="预览失败或超过资源限制，请检查文件或拆分后重试")
            result = json.loads(output)
            if "error" in result:
                raise BadRequestError(message=result["error"])
            return result
        finally:
            if process is not None and process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                await process.wait()
            fcntl.flock(lock, fcntl.LOCK_UN)
