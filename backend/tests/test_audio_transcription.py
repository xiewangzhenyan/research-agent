"""Cloud ASR contract, billing bounds, isolation and hostile-input regressions."""

import asyncio
import io
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from redis.exceptions import ConnectionError as RedisConnectionError

from app.api.deps import get_current_user
from app.core.config import Settings, settings
from app.core.exceptions import BadRequestError, ExternalServiceError, RateLimitError
from app.main import app
from app.services import audio_transcription as audio

pytestmark = pytest.mark.anyio


def wav(seconds=1, *, rate=16000, channels=1):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as file:
        file.setnchannels(channels)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes(b"\x00\x01" * int(seconds * rate * channels))
    return buffer.getvalue()


@pytest.fixture
def service():
    redis = MagicMock()
    redis.raw.set = AsyncMock(return_value=True)
    redis.raw.eval = AsyncMock(return_value=1)
    config = Settings(_env_file=None, ASR_ENABLED=True, ASR_API_KEY=SecretStr("test-only-secret"))
    return audio.AudioTranscriptionService(redis, config)


@pytest.fixture
def provider(monkeypatch):
    original_client = httpx.AsyncClient
    requests = []
    replies = [httpx.Response(200, json={"text": " 光学 LSPR "})]

    async def handle(request):
        requests.append(request)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(
        audio.httpx,
        "AsyncClient",
        lambda **kw: original_client(**kw, transport=httpx.MockTransport(handle)),
    )
    return requests, replies


async def test_primary_only_and_server_selected_model(service, provider):
    requests, _ = provider
    result = await service.transcribe(wav(), uuid4())
    assert result.text == "光学 LSPR"
    assert result.model == "Qwen/Qwen3-ASR-1.7B"
    assert not result.used_fallback
    assert len(requests) == 1
    assert b"Qwen/Qwen3-ASR-1.7B" in requests[0].content
    assert requests[0].headers["content-type"].startswith("multipart/form-data;")
    assert requests[0].headers["authorization"] == "Bearer test-only-secret"
    # One duration reservation and a compare-and-delete release.
    assert service.redis.raw.eval.await_count == 2
    assert "test-only-secret" not in repr(service.config)


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(404),
        httpx.Response(429),
        httpx.Response(503),
        httpx.Response(504),
        httpx.Response(200, text="invalid-json"),
        httpx.Response(200, json={"text": 7}),
        httpx.Response(200, content=b"x" * (audio.MAX_RESPONSE_BYTES + 1)),
        httpx.ReadTimeout("private-provider-details"),
    ],
)
async def test_temporary_failure_falls_back_exactly_once(service, provider, failure, caplog):
    requests, replies = provider
    replies[:] = [
        failure,
        httpx.Response(
            200, json={"text": "备用结果"}, headers={"x-siliconcloud-trace-id": "trace_test-123"}
        ),
    ]
    result = await service.transcribe(wav(), uuid4())
    assert result.model == "XingChenAGI/XingChenASR-V3.2-Ultra"
    assert result.used_fallback and result.trace_id == "trace_test-123"
    assert len(requests) == 2
    assert service.redis.raw.eval.await_count == 3
    assert "test-only-secret" not in caplog.text
    assert "private-provider-details" not in caplog.text


@pytest.mark.parametrize("status", [400, 401, 402, 403, 413, 422])
async def test_permanent_errors_do_not_trigger_paid_retry(service, provider, status):
    requests, replies = provider
    replies[:] = [httpx.Response(status, json={"error": "private-provider-details"})]
    with pytest.raises(ExternalServiceError) as error:
        await service.transcribe(wav(), uuid4())
    assert "private-provider-details" not in str(error.value)
    assert len(requests) == 1


async def test_both_failures_are_bounded_and_lock_is_released(service, provider):
    requests, replies = provider
    replies[:] = [httpx.Response(503), httpx.Response(503)]
    with pytest.raises(ExternalServiceError):
        await service.transcribe(wav(), uuid4())
    assert len(requests) == 2
    assert service.redis.raw.eval.call_args.args[0] == audio._RELEASE


async def test_empty_text_is_silence_not_a_reason_to_retry(service, provider):
    requests, replies = provider
    replies[:] = [httpx.Response(200, json={"text": " "})]
    assert (await service.transcribe(wav(), uuid4())).text == ""
    assert len(requests) == 1


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not-audio",
        wav(0.1),
        wav(61),
        wav(rate=8000),
        wav(channels=2),
        wav()[:-20],
        b"x" * (audio.MAX_AUDIO_BYTES + 1),
    ],
)
async def test_invalid_audio_is_rejected_before_metering_or_provider(service, provider, data):
    with pytest.raises(BadRequestError):
        await service.transcribe(data, uuid4())
    service.redis.raw.set.assert_not_awaited()
    assert not provider[0]


async def test_per_account_lock_and_quota(service, provider):
    uid = uuid4()
    service.redis.raw.set.return_value = False
    with pytest.raises(RateLimitError, match="上一段"):
        await service.transcribe(wav(), uid)
    assert service.redis.raw.set.call_args.args[0].endswith(str(uid))
    service.redis.raw.eval.assert_not_awaited()  # Never unlock someone else's lease.
    service.redis.raw.set.return_value = True
    service.redis.raw.eval.side_effect = [0, 1]
    with pytest.raises(RateLimitError, match="额度"):
        await service.transcribe(wav(), uid)
    reservation = service.redis.raw.eval.call_args_list[0].args
    assert str(uid) in reservation[2]
    assert not provider[0]


async def test_meter_unavailable_fails_closed(service, provider):
    service.redis.raw.set.side_effect = RedisConnectionError("private-host")
    with pytest.raises(ExternalServiceError) as error:
        await service.transcribe(wav(), uuid4())
    assert "private-host" not in str(error.value)
    assert not provider[0]


async def test_disabled_has_no_provider_or_redis_calls(service, provider):
    service.config.ASR_ENABLED = False
    with pytest.raises(ExternalServiceError, match="尚未配置"):
        await service.transcribe(wav(), uuid4())
    assert not provider[0]
    service.redis.raw.set.assert_not_awaited()


async def test_cancellation_releases_lock_without_fallback(service, monkeypatch):
    entered = asyncio.Event()

    async def pending(*args):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "_request", pending)
    task = asyncio.create_task(service.transcribe(wav(), uuid4()))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert service.redis.raw.eval.call_args.args[0] == audio._RELEASE
    assert service.redis.raw.eval.await_count == 2


async def test_api_requires_login(client):
    assert (await client.get("/api/v1/audio/config")).status_code == 401
    response = await client.post(
        "/api/v1/audio/transcriptions", content=wav(), headers={"content-type": "audio/wav"}
    )
    assert response.status_code == 401


async def test_api_scope_config_and_body_limits(client, monkeypatch):
    user = SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(settings, "ASR_ENABLED", True)
    monkeypatch.setattr(settings, "ASR_API_KEY", SecretStr("test-only-secret"))
    config = await client.get("/api/v1/audio/config")
    assert config.status_code == 200
    assert config.json()["model"] == "Qwen/Qwen3-ASR-1.7B"
    assert "test-only-secret" not in config.text and "ASR_API_KEY" not in config.text
    assert config.headers["cache-control"] == "private, no-store"
    transcribe = AsyncMock(
        return_value=audio.TranscriptionResult(
            text="测试",
            model="Qwen/Qwen3-ASR-1.7B",
            used_fallback=False,
            duration_seconds=1,
        )
    )
    monkeypatch.setattr(audio.AudioTranscriptionService, "transcribe", transcribe)
    response = await client.post(
        "/api/v1/audio/transcriptions", content=wav(), headers={"content-type": "audio/wav"}
    )
    assert response.status_code == 200
    transcribe.assert_awaited_once_with(wav(), user.id)
    for body, headers, status in [
        (wav(), {"content-type": "audio/webm"}, 415),
        (b"x" * (audio.MAX_AUDIO_BYTES + 1), {"content-type": "audio/wav"}, 413),
    ]:
        response = await client.post("/api/v1/audio/transcriptions", content=body, headers=headers)
        assert response.status_code == status

    async def chunks():
        yield b"x" * audio.MAX_AUDIO_BYTES
        yield b"x"

    response = await client.post(
        "/api/v1/audio/transcriptions", content=chunks(), headers={"content-type": "audio/wav"}
    )
    assert response.status_code == 413
    assert transcribe.await_count == 1
