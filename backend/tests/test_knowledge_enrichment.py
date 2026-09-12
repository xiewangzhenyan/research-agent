"""Re-ranking ordering and independently attributable, bounded neighboring evidence."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import ValidationError

from app.core.exceptions import BadRequestError
from app.schemas.knowledge import RetrievalConfig
from app.services.knowledge_enrichment import (
    RERANK_MODEL,
    RERANK_REVISION,
    expand_context,
    rerank_candidates,
)
from app.services.knowledge_index import rank_chunks


def chunk(i, *, doc="a", generation="one", page=None, location=None, content=None):
    return {
        "id": f"{doc}-{generation}-{i}",
        "document_id": doc,
        "knowledge_base_id": "owned",
        "index_generation": generation,
        "position": i,
        "page": page,
        "location": location or {},
        "content": content or f"原文{i}",
        "embedding": [1, 0],
        "index": i + 1,
        "score": 0.01,
        "score_type": "rrf",
        "retrieval": {
            "keyword_score": 1,
            "semantic_score": 1,
            "keyword_rank": i + 1,
            "semantic_rank": i + 1,
        },
    }


@pytest.mark.parametrize(
    "settings",
    [
        {"rerank_limit": 21},
        {"rerank_enabled": "true"},
        {"context_window": 3},
        {"context_char_budget": 2001},
        {"context_enabled": 1},
    ],
)
def test_limits_and_boolean_types(settings):
    with pytest.raises(ValidationError):
        RetrievalConfig.model_validate(settings)


def test_old_saved_preferences_keep_enrichment_disabled():
    config = RetrievalConfig.model_validate({"mode": "keyword"})
    assert not config.context_enabled and not config.rerank_enabled


def test_neighbors_are_separate_sources_with_correct_pages_and_no_vectors():
    before, seed, after = [chunk(i, page=i + 1) for i in range(3)]
    seed["index"] = 1
    stats = {}
    result = expand_context(
        [seed], [before, seed, after], RetrievalConfig(context_enabled=True), stats
    )
    assert [x["page"] for x in result] == [2, 1, 3]
    assert [x["index"] for x in result] == [1, 2, 3]
    assert result[1]["context_of"] == [seed["id"]]
    assert result[1]["content"] == before["content"] and "embedding" not in result[1]
    assert result[1]["score_type"] == "context" and result[1]["retrieval"]["semantic_score"] is None
    assert stats["context"]["added"] == 2


def test_neighbors_cannot_cross_document_generation_section_or_table():
    seed = chunk(1, location={"section": "正文"})
    candidates = [
        chunk(0, doc="other"),
        chunk(2, generation="new"),
        chunk(0, location={"section": "附录"}),
        chunk(2, location={"section": "正文", "table": 1}),
    ]
    result = expand_context([seed], candidates, RetrievalConfig(context_enabled=True), {})
    assert result == [seed]


def test_shared_neighbors_and_seed_hits_are_never_duplicated():
    chunks = [chunk(i) for i in range(5)]
    stats = {}
    result = expand_context(
        [chunks[1], chunks[3]], chunks, RetrievalConfig(context_enabled=True), stats
    )
    assert len(result) == len({x["id"] for x in result}) == 5
    shared = next(x for x in result if x["id"] == chunks[2]["id"])
    assert set(shared["context_of"]) == {chunks[1]["id"], chunks[3]["id"]}


def test_budget_keeps_whole_chunks_and_ten_source_limit():
    chunks = [chunk(i, content="x" * 400) for i in range(30)]
    stats = {}
    result = expand_context(
        [chunks[1]], chunks, RetrievalConfig(context_enabled=True, context_char_budget=500), stats
    )
    assert len(result) == 2 and stats["context"]["added_chars"] == 400
    seeds = chunks[::3]
    assert len(seeds) == 10
    result = expand_context(seeds, chunks, RetrievalConfig(context_enabled=True), {})
    assert len(result) == 10


@pytest.mark.asyncio
async def test_rerank_precedes_overlap_deduplication_and_preserves_original_rank():
    chunks = [chunk(i) for i in range(3)]
    stats = {}
    candidates = rank_chunks("原文", [1, 0], chunks, top_k=10, diagnostics=stats, deduplicate=False)
    assert len(candidates) == 3
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "http://local/rank"),
        json={
            "scores": [-1, 7, 1],
            "model": RERANK_MODEL,
            "revision": RERANK_REVISION,
            "truncated_pairs": 0,
        },
    )
    with patch("httpx.AsyncClient.post", AsyncMock(return_value=response)):
        result = await rerank_candidates("原文", candidates, 6, stats)
    assert len(result) == 1 and result[0]["id"] == candidates[1]["id"]
    assert result[0]["retrieval"]["initial_rank"] == 2 and result[0]["score"] == 7
    assert result[0]["score_type"] == "reranker" and stats["overlap_removed"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scores,model", [([1], RERANK_MODEL), ([1, "nan"], RERANK_MODEL), ([1, 2], "wrong")]
)
async def test_invalid_model_output_fails_closed(scores, model):
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "http://local/rank"),
        json={"scores": scores, "model": model, "revision": RERANK_REVISION},
    )
    with (
        patch("httpx.AsyncClient.post", AsyncMock(return_value=response)),
        pytest.raises(BadRequestError),
    ):
        await rerank_candidates("原文", [chunk(0), chunk(1)], 1, {})


@pytest.mark.asyncio
async def test_unavailable_reranker_does_not_silently_return_old_ranking():
    with (
        patch("httpx.AsyncClient.post", AsyncMock(side_effect=httpx.ConnectError("unavailable"))),
        pytest.raises(BadRequestError),
    ):
        await rerank_candidates("原文", [chunk(0)], 1, {})
