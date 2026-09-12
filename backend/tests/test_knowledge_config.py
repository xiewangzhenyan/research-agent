"""Processing configuration validation and actual chunking behavior."""

from itertools import pairwise

import pytest
from pydantic import ValidationError

from app.schemas.knowledge import ChunkingConfig
from app.services.knowledge_index import parse_blocks, rank_chunks, split_blocks


@pytest.mark.parametrize(
    "values",
    [
        {"chunk_size": 255},
        {"chunk_size": 501},
        {"chunk_size": True},
        {"chunk_size": 300.5},
        {"chunk_overlap": -1},
        {"chunk_overlap": 129},
        {"chunk_size": 256, "chunk_overlap": 128},
        {"unknown_option": 1},
    ],
)
def test_unsafe_or_ambiguous_configuration_rejected(values):
    with pytest.raises(ValidationError):
        ChunkingConfig.model_validate(values)


def test_zero_overlap_preserves_text_without_duplicate_characters():
    config = ChunkingConfig(chunk_size=300, chunk_overlap=0)
    text = "abcdefghijklmnopqrstuvwxyz" * 50
    chunks = split_blocks(
        [{"page": 2, "text": text, "location": {}}],
        size=config.chunk_size,
        overlap=config.chunk_overlap,
    )
    assert "".join(c["content"] for c in chunks) == text
    assert len(chunks) == 5 and all(len(c["content"]) <= 300 for c in chunks)
    assert all(c["page"] == 2 for c in chunks)


def test_custom_overlap_is_used_and_default_behavior_is_compatible():
    blocks = [{"page": None, "text": "abcdefghij" * 100, "location": {}}]
    chunks = split_blocks(blocks, size=300, overlap=20)
    assert all(a["content"][-20:] == b["content"][:20] for a, b in pairwise(chunks))
    assert split_blocks(blocks) == split_blocks(blocks, size=450, overlap=65)


def test_long_table_cells_keep_headers_at_smallest_supported_size():
    blocks = parse_blocks(("表头" * 95 + "\n" + "数据" * 400).encode(), "table.csv")
    chunks = split_blocks(blocks, size=256, overlap=100)
    assert all(len(c["content"]) <= 256 and c["content"].startswith("表头：") for c in chunks)
    assert "".join(c["content"].split("\n", 1)[1] for c in chunks) == "数据" * 400


def test_zero_overlap_index_does_not_collapse_independent_neighbors():
    chunks = [
        {
            "document_id": "a",
            "position": i,
            "page": 1,
            "location": {},
            "content": f"独立数据 {i}",
            "embedding": [1, 0],
            "chunking_config": {"chunk_size": 300, "chunk_overlap": 0},
        }
        for i in range(3)
    ]
    assert len(rank_chunks("独立数据", [1, 0], chunks)) == 3
