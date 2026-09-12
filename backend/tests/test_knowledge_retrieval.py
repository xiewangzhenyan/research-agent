"""Controllable ranking must reflect actual scores, scope and disabled branches."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.knowledge import RetrievalConfig
from app.services.knowledge import KnowledgeService
from app.services.knowledge_index import rank_chunks


def corpus(n=5):
    return [
        {
            "id": str(i),
            "document_id": str(i),
            "position": 0,
            "content": "exact-policy" if i == 0 else f"unrelated {i}",
            "embedding": [0, 1] if i == 0 else [1, 0],
        }
        for i in range(n)
    ]


@pytest.mark.parametrize(
    "values",
    [
        {"mode": "unknown"},
        {"candidate_limit": 101},
        {"result_limit": 0},
        {"candidate_limit": True},
        {"result_limit": 2.5},
        {"rrf_k": 0},
        {"semantic_threshold": -0.1},
        {"semantic_threshold": 1.1},
        {"keyword_threshold": float("nan")},
        {"keyword_weight": float("inf")},
        {"keyword_weight": True},
        {"semantic_weight": 0, "keyword_weight": 0},
        {"extra": 1},
    ],
)
def test_invalid_settings_rejected(values):
    with pytest.raises(ValidationError):
        RetrievalConfig.model_validate(values)


def test_keyword_search_ignores_vectors_and_reports_only_lexical_candidates():
    chunks = [{k: v for k, v in c.items() if k != "embedding"} for c in corpus()]
    stats = {}
    hits = rank_chunks(
        "exact-policy", [], chunks, config=RetrievalConfig(mode="keyword"), diagnostics=stats
    )
    assert [h["id"] for h in hits] == ["0"]
    assert hits[0]["score_type"] == "bm25"
    assert hits[0]["retrieval"]["semantic_score"] is None
    assert stats["semantic_candidates"] == 0 and stats["keyword_candidates"] == 1


def test_semantic_mode_does_not_admit_keyword_only_hit():
    stats = {}
    hits = rank_chunks(
        "exact-policy", [1, 0], corpus(), config=RetrievalConfig(mode="semantic"), diagnostics=stats
    )
    assert "0" not in {h["id"] for h in hits}
    assert all(h["score"] == 1 and h["score_type"] == "cosine" for h in hits)
    assert stats["keyword_candidates"] == 0


def test_weighted_rrf_changes_order_and_zero_disables_branch():
    low = rank_chunks("exact-policy", [1, 0], corpus(), config=RetrievalConfig(keyword_weight=0.1))
    high = rank_chunks("exact-policy", [1, 0], corpus(), config=RetrievalConfig(keyword_weight=2))
    assert low[0]["id"] != "0" and high[0]["id"] == "0"
    stats = {}
    hits = rank_chunks(
        "exact-policy", [], corpus(), config=RetrievalConfig(semantic_weight=0), diagnostics=stats
    )
    assert [h["id"] for h in hits] == ["0"] and stats["semantic_eligible"] == 0
    assert hits[0]["score"] == round(1 / 61, 6)


def test_thresholds_depth_and_diagnostic_accounting():
    stats = {}
    hits = rank_chunks(
        "exact-policy",
        [1, 0],
        corpus(25),
        top_k=3,
        config=RetrievalConfig(candidate_limit=10, keyword_threshold=100),
        diagnostics=stats,
    )
    assert len(hits) == 3 and stats["semantic_eligible"] == 24
    assert stats["semantic_candidates"] == 10 and stats["keyword_candidates"] == 0
    assert (
        stats["merged_candidates"]
        == stats["returned"] + stats["overlap_removed"] + stats["limit_removed"]
    )
    assert stats["limit_removed"] == 7


def test_diagnostics_count_overlap_and_empty_scope():
    chunks = [c | {"document_id": "one", "position": i} for i, c in enumerate(corpus())]
    stats = {}
    rank_chunks("exact-policy", [1, 0], chunks, diagnostics=stats)
    assert stats["overlap_removed"] > 0
    stats = {}
    assert rank_chunks("empty", [], [], diagnostics=stats) == []
    assert stats["total_chunks"] == stats["returned"] == 0


@pytest.mark.anyio
async def test_keyword_service_does_not_load_embedding_model():
    service = KnowledgeService(AsyncMock(), uuid4())
    service.get_retrieval_config = AsyncMock(return_value=RetrievalConfig(mode="keyword"))
    service.validate_scope = AsyncMock()
    from types import SimpleNamespace

    chunk = SimpleNamespace(
        id=uuid4(), position=0, page=None, location={}, content="exact-policy", embedding=None
    )
    document = SimpleNamespace(
        id=uuid4(),
        knowledge_base_id=uuid4(),
        filename="guide.txt",
        title="guide.txt",
        source_kind="file",
        revision=1,
        parse_report=None,
        chunking_config=None,
        sha256="hash",
        job_id=uuid4(),
    )
    service.db.execute.return_value.all = lambda: [(chunk, document, "Owned")]
    with patch("app.services.knowledge.embed", side_effect=AssertionError("No embedding allowed")):
        stats = {}
        hits = await service.search([document.knowledge_base_id], "exact-policy", diagnostics=stats)
    assert hits[0]["score_type"] == "bm25" and stats["embedding_ms"] == 0
    service.validate_scope.assert_awaited_once()
