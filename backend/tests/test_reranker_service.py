"""Exercise the private ASGI boundary and real background-thread gate lifecycle."""

import asyncio
import threading
from types import SimpleNamespace

import httpx
import pytest

from app.reranker import main as service


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setattr(service, "gate", threading.Lock())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=service.app), base_url="http://local"
    ) as client:
        yield client


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {"query": " ", "documents": ["text"]},
        {"query": "q", "documents": ["x" * 501]},
        {"query": "q", "documents": []},
        {"query": "q", "documents": ["x"] * 21},
        {"query": "q", "documents": [" "]},
        {"query": "q", "documents": ["x"], "extra": True},
    ],
)
async def test_invalid_input_does_not_acquire_gate(client, payload):
    assert (await client.post("/rank", json=payload)).status_code == 422
    assert not service.gate.locked()


@pytest.mark.anyio
async def test_size_limit_and_busy(client):
    assert (await client.post("/rank", content=b"x" * (128 * 1024 + 1))).status_code == 413
    service.gate.acquire()
    try:
        assert (
            await client.post("/rank", json={"query": "q", "documents": ["x"]})
        ).status_code == 429
    finally:
        service.gate.release()


@pytest.mark.anyio
@pytest.mark.parametrize("cancel", [False, True])
async def test_timeout_or_cancellation_keeps_gate_until_thread_finishes(
    client, monkeypatch, cancel
):
    started, release = threading.Event(), threading.Event()

    def inference(*args, **kwargs):
        started.set()
        release.wait(3)
        return [1.5]

    fake = SimpleNamespace(
        model=SimpleNamespace(
            tokenizer=SimpleNamespace(
                encode_batch=lambda pairs: [SimpleNamespace(overflowing=[]) for _ in pairs]
            )
        ),
        rerank=inference,
    )
    monkeypatch.setattr(service, "model", fake)
    monkeypatch.setattr(service, "INFERENCE_TIMEOUT", 0.1)
    task = asyncio.create_task(client.post("/rank", json={"query": "q", "documents": ["x"]}))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            assert (await task).status_code == 504
        assert service.gate.locked()
        assert (
            await client.post("/rank", json={"query": "q", "documents": ["x"]})
        ).status_code == 429
    finally:
        release.set()
        await asyncio.gather(*service.inflight, return_exceptions=True)
    assert not service.gate.locked()
    response = await client.post("/rank", json={"query": "q", "documents": ["x"]})
    assert response.status_code == 200 and response.json()["scores"] == [1.5]


@pytest.mark.anyio
async def test_inference_failure_releases_gate(client, monkeypatch):
    monkeypatch.setattr(service, "model", None)
    assert (await client.post("/rank", json={"query": "q", "documents": ["x"]})).status_code == 503
    assert not service.gate.locked()
