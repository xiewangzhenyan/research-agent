"""Bounded cloud ASR. Audio and transcripts are never persisted or logged here."""

import asyncio
import io
import json
import logging
import math
import re
import wave
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel
from redis.exceptions import RedisError

from app.clients.redis import RedisClient
from app.core.config import Settings, settings
from app.core.exceptions import BadRequestError, ExternalServiceError, RateLimitError

logger = logging.getLogger(__name__)
MAX_AUDIO_BYTES = 2 * 1024 * 1024
MAX_AUDIO_SECONDS = 60
MAX_RESPONSE_BYTES = 128 * 1024
_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""
_RESERVE = """
local used = tonumber(redis.call('GET', KEYS[1]) or '0')
local seconds = tonumber(ARGV[1])
if used + seconds > tonumber(ARGV[2]) then return 0 end
redis.call('INCRBY', KEYS[1], seconds)
redis.call('EXPIRE', KEYS[1], 172800)
return 1
"""


class TranscriptionResult(BaseModel):
    text: str
    model: str
    used_fallback: bool
    duration_seconds: float
    trace_id: str | None = None


def audio_config() -> dict:
    """Read configuration only: never probe the provider or expose credentials."""
    return {
        "provider": "siliconflow",
        "enabled": bool(settings.ASR_ENABLED and settings.ASR_API_KEY.get_secret_value()),
        "model": settings.ASR_MODEL,
        "fallback_model": settings.ASR_FALLBACK_MODEL or None,
        "max_duration_seconds": MAX_AUDIO_SECONDS,
        "daily_audio_seconds": settings.ASR_DAILY_AUDIO_SECONDS,
    }


def validate_audio(data: bytes) -> float:
    """Only accept bounded decoded PCM, not compressed bytes or a claimed duration."""
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise BadRequestError(message="录音为空或超过 2 MB，请重新录制", code="ASR_INVALID_AUDIO")
    try:
        with wave.open(io.BytesIO(data)) as wav:
            if (
                wav.getnchannels() != 1
                or wav.getsampwidth() != 2
                or wav.getframerate() != 16000
                or wav.getcomptype() != "NONE"
            ):
                raise ValueError("Unsupported PCM format")
            count = wav.getnframes()
            duration = count / 16000
            if not 0.25 <= duration <= MAX_AUDIO_SECONDS:
                raise ValueError("Duration outside bounds")
            if len(wav.readframes(count)) != count * 2:
                raise ValueError("Truncated PCM")
    except (wave.Error, EOFError, ValueError, OSError) as exc:
        raise BadRequestError(
            message="录音格式无效，请录制 0.25 至 60 秒的音频后重试", code="ASR_INVALID_AUDIO"
        ) from exc
    return duration


class _ProviderFailure(Exception):
    def __init__(self, status: int = 502, trace_id: str | None = None):
        self.status = status
        self.trace_id = trace_id

    @property
    def retryable(self) -> bool:
        return self.status in {404, 408, 429} or self.status >= 500


class AudioTranscriptionService:
    def __init__(self, redis: RedisClient, config: Settings = settings):
        self.redis = redis
        self.config = config

    async def transcribe(self, data: bytes, user_id: UUID) -> TranscriptionResult:
        config = self.config
        if not config.ASR_ENABLED or not config.ASR_API_KEY.get_secret_value():
            raise ExternalServiceError(
                message="语音转写尚未配置，请联系管理员", code="ASR_NOT_CONFIGURED"
            )
        duration = validate_audio(data)
        # One recording per account, shared across tabs and server workers.
        lock = f"asr:v1:active:{user_id}"
        token = str(uuid4())
        acquired = False
        try:
            async with asyncio.timeout(3):
                acquired = bool(await self.redis.raw.set(lock, token, nx=True, ex=110))
            if not acquired:
                raise RateLimitError(message="上一段录音仍在转写，请稍后重试", code="ASR_BUSY")
            models = list(
                dict.fromkeys(filter(None, [config.ASR_MODEL, config.ASR_FALLBACK_MODEL]))
            )
            # No hidden SDK retries. At most two paid calls.
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(config.ASR_TIMEOUT_SECONDS, connect=5),
                trust_env=False,
                follow_redirects=False,
            ) as client:
                for index, model in enumerate(models):
                    await self._reserve_seconds(user_id, math.ceil(duration))
                    try:
                        text, trace_id = await self._request(client, data, model)
                        return TranscriptionResult(
                            text=text,
                            model=model,
                            used_fallback=index > 0,
                            duration_seconds=duration,
                            trace_id=trace_id,
                        )
                    except _ProviderFailure as exc:
                        # Only codes and a constrained provider trace ID, never body/key/audio.
                        logger.warning(
                            "ASR attempt failed model=%s status=%s trace_id=%s",
                            model,
                            exc.status,
                            exc.trace_id,
                        )
                        if not exc.retryable or index + 1 == len(models):
                            if exc.status in {401, 402, 403}:
                                raise ExternalServiceError(
                                    message="语音服务鉴权或额度异常，请联系管理员",
                                    code="ASR_PROVIDER_CONFIG",
                                ) from None
                            raise ExternalServiceError(
                                message="语音转写暂时失败，录音已保留，可点击重试",
                                code="ASR_UNAVAILABLE",
                            ) from None
        except (RedisError, RuntimeError, TimeoutError):
            # No unmetered calls if the shared quota/lock store is unavailable.
            raise ExternalServiceError(
                message="语音服务暂时不可用，请稍后重试", code="ASR_UNAVAILABLE"
            ) from None
        finally:
            if acquired:
                try:
                    async with asyncio.timeout(3):
                        await self.redis.raw.eval(_RELEASE, 1, lock, token)
                except (RedisError, RuntimeError, TimeoutError):
                    logger.warning("ASR lease release failed; lease will expire")
        raise ExternalServiceError(message="语音模型未配置", code="ASR_NOT_CONFIGURED")

    async def _reserve_seconds(self, user_id: UUID, seconds: int) -> None:
        day = datetime.now(UTC).strftime("%Y%m%d")
        async with asyncio.timeout(3):
            allowed = await self.redis.raw.eval(
                _RESERVE,
                1,
                f"asr:v1:seconds:{user_id}:{day}",
                str(seconds),
                str(self.config.ASR_DAILY_AUDIO_SECONDS),
            )
        if not allowed:
            raise RateLimitError(
                message="今日语音转写额度已用完，请使用文字输入", code="ASR_DAILY_LIMIT"
            )

    async def _request(
        self, client: httpx.AsyncClient, data: bytes, model: str
    ) -> tuple[str, str | None]:
        try:
            async with (
                asyncio.timeout(self.config.ASR_TIMEOUT_SECONDS),
                client.stream(
                    "POST",
                    f"{self.config.ASR_BASE_URL}/audio/transcriptions",
                    headers={
                        "Authorization": f"Bearer {self.config.ASR_API_KEY.get_secret_value()}"
                    },
                    data={"model": model},
                    files={"file": ("recording.wav", data, "audio/wav")},
                ) as response,
            ):
                trace = response.headers.get("x-siliconcloud-trace-id", "")
                trace_id = trace if re.fullmatch(r"[\w-]{1,120}", trace, flags=re.ASCII) else None
                if response.status_code != 200:
                    raise _ProviderFailure(response.status_code, trace_id)
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise _ProviderFailure(502, trace_id)
                payload = json.loads(body)
                if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
                    raise _ProviderFailure(502, trace_id)
                # Empty text is valid silence; another model could invent words.
                return payload["text"].strip(), trace_id
        except (httpx.HTTPError, TimeoutError, ValueError):
            raise _ProviderFailure() from None
