"""Authenticated short voice input. Browser PCM is forwarded as provider multipart."""

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.deps import CurrentUser, DBSession, Redis
from app.services.audio_transcription import (
    MAX_AUDIO_BYTES,
    AudioTranscriptionService,
    TranscriptionResult,
    audio_config,
)

router = APIRouter(prefix="/audio", tags=["audio"])


@router.get("/config")
async def get_audio_config(current_user: CurrentUser, response: Response) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    return audio_config()


@router.post(
    "/transcriptions",
    response_model=TranscriptionResult,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def transcribe_audio(
    current_user: CurrentUser, redis: Redis, db: DBSession, request: Request, response: Response
) -> TranscriptionResult:
    response.headers["Cache-Control"] = "private, no-store"
    user_id = current_user.id
    # Authentication has finished its read. Do not hold a pooled DB connection
    # while receiving audio or waiting for a remote model; this route writes no DB data.
    await db.rollback()
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "audio/wav":
        raise HTTPException(415, "请使用浏览器录音生成的 WAV 音频")
    length = request.headers.get("content-length")
    if length and (not length.isdecimal() or int(length) > MAX_AUDIO_BYTES):
        raise HTTPException(413, "录音不能超过 2 MB")
    data = bytearray()
    try:
        async with asyncio.timeout(15):
            async for chunk in request.stream():
                if len(data) + len(chunk) > MAX_AUDIO_BYTES:
                    raise HTTPException(413, "录音不能超过 2 MB")
                data.extend(chunk)
    except TimeoutError:
        raise HTTPException(408, "录音上传超时，请重试") from None
    return await AudioTranscriptionService(redis).transcribe(bytes(data), user_id)
