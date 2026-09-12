"""One resident ONNX model, bounded inputs and no document storage or outbound network."""

import asyncio
import math
import threading
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request
from fastembed.rerank.cross_encoder import TextCrossEncoder
from pydantic import BaseModel, ConfigDict, Field, ValidationError

MODEL = "BAAI/bge-reranker-base"
REVISION = "2cfc18c9415c912f9d8155881c133215df768a70"
model = None
gate = threading.Lock()
INFERENCE_TIMEOUT = 40
inflight: set[asyncio.Task] = set()


class RankRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=1500)
    documents: list[str] = Field(min_length=1, max_length=20)


@asynccontextmanager
async def lifespan(app):
    global model
    model = TextCrossEncoder(
        MODEL,
        specific_model_path="/models/bge-reranker-base",
        local_files_only=True,
        threads=2,
        providers=["CPUExecutionProvider"],
    )
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
async def health():
    if model is None:
        raise HTTPException(503, "Model not ready")
    return {"status": "healthy", "model": MODEL, "revision": REVISION}


def score(body):
    try:
        started = perf_counter()
        encodings = model.model.tokenizer.encode_batch(
            [(body.query, doc) for doc in body.documents]
        )
        truncated = sum(bool(item.overflowing) for item in encodings)
        scores = list(model.rerank(body.query, body.documents, batch_size=1))
        if len(scores) != len(body.documents) or not all(math.isfinite(s) for s in scores):
            raise ValueError("Invalid model output")
        return {
            "scores": scores,
            "model": MODEL,
            "revision": REVISION,
            "truncated_pairs": truncated,
            "max_tokens": 512,
            "inference_ms": round((perf_counter() - started) * 1000),
        }
    finally:
        gate.release()


@app.post("/rank")
async def rank(request: Request):
    data = bytearray()
    async for part in request.stream():
        data.extend(part)
        if len(data) > 128 * 1024:
            raise HTTPException(413, "Request too large")
    try:
        body = RankRequest.model_validate_json(data)
    except ValidationError as exc:
        raise HTTPException(422, "Invalid ranking request") from exc
    if not body.query.strip() or any(not doc.strip() or len(doc) > 500 for doc in body.documents):
        raise HTTPException(422, "Invalid ranking text")
    if not gate.acquire(blocking=False):
        raise HTTPException(429, "Reranker busy")
    task = asyncio.create_task(asyncio.to_thread(score, body))
    inflight.add(task)
    task.add_done_callback(inflight.discard)
    # A disconnected caller cannot release the gate while ONNX is still using it.
    task.add_done_callback(
        lambda finished: finished.exception() if not finished.cancelled() else None
    )
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=INFERENCE_TIMEOUT)
    except TimeoutError as exc:
        raise HTTPException(504, "Reranker timed out") from exc
    except Exception as exc:
        raise HTTPException(503, "Reranker unavailable") from exc
