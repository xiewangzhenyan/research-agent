"""Small account-scoped pgvector memory index using the existing offline encoder."""

import asyncio
import logging

import numpy as np

from app.services.knowledge_index import embed
from app.services.knowledge_search_index import QUERY_PREFIX, model_fingerprint

logger = logging.getLogger(__name__)


def fingerprint():
    return "memory-mean320-v1:" + model_fingerprint()


def encode_note(title, content):
    # Encode every part, not just the model's first token window. Recall still
    # injects the complete note, so retrieval chunking cannot cut a constraint.
    vectors = embed([title + "\n" + content[i : i + 320] for i in range(0, len(content), 320)])
    vector = np.mean(np.asarray(vectors, dtype=np.float32), axis=0)
    norm = np.linalg.norm(vector)
    if vector.shape != (512,) or not np.isfinite(vector).all() or norm <= 0:
        raise ValueError("Invalid local embedding")
    return (vector / norm).astype(float).tolist(), fingerprint()


def encode_query(query):
    vector = embed([QUERY_PREFIX + query[:1500]])[0]
    if len(vector) != 512 or not np.isfinite(vector).all():
        raise ValueError("Invalid local query embedding")
    return vector, fingerprint()


# One in-flight query per API process. A timeout does not release the slot while
# native ONNX code is still running in its thread; avoid accumulating inference.
_query_task = None


async def query_vector(query):
    global _query_task
    if _query_task is not None and not _query_task.done():
        raise TimeoutError("Local embedding busy")
    _query_task = asyncio.create_task(asyncio.to_thread(encode_query, query))
    _query_task.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
    return await asyncio.wait_for(asyncio.shield(_query_task), timeout=3)
