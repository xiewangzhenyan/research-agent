"""Task parameter identity and bounded records of actual retrieval execution."""

import hashlib
import json

from app.schemas.knowledge import RetrievalConfig, RetrievalSnapshot


def configuration_id(config):
    return hashlib.sha256(
        json.dumps({"schema_version": 1, "config": config.model_dump()}, sort_keys=True).encode()
    ).hexdigest()


def capture(config: RetrievalConfig, *, override=False, collaboration=False):
    config = RetrievalConfig.model_validate(config.model_dump())
    capped = collaboration and config.result_limit > 5
    if capped:
        config = config.model_copy(update={"result_limit": 5})
    return RetrievalSnapshot(
        configuration_id=configuration_id(config),
        origin="task_override" if override else "account",
        config=config,
        result_limit_capped=capped,
    ).model_dump()


def restore(snapshot):
    if snapshot is None:
        return None  # Historical tasks never claimed to pin submission-time parameters.
    value = RetrievalSnapshot.model_validate(snapshot)
    if value.configuration_id != configuration_id(value.config):
        raise ValueError("Retrieval snapshot identity mismatch")
    return value.config


def execution_record(query, diagnostics):
    config = RetrievalConfig.model_validate(diagnostics["config"])
    # Only copy fields from this public allowlist, never internal endpoints or credentials.
    record = {
        "query": query,
        "configuration_id": configuration_id(config),
        "config": config.model_dump(),
        **{
            key: diagnostics[key]
            for key in (
                "engine",
                "vector_search",
                "tokenizer",
                "model_fingerprint",
                "total_chunks",
                "indexed_chunks",
                "returned",
                "total_ms",
                "embedding_ms",
                "keyword_candidates",
                "semantic_candidates",
                "merged_candidates",
            )
            if key in diagnostics
        },
    }
    for key, fields in {
        "rerank": (
            "status",
            "model",
            "revision",
            "candidates",
            "elapsed_ms",
            "truncated_pairs",
            "max_tokens",
        ),
        "context": (
            "enabled",
            "seed_count",
            "added",
            "added_chars",
            "budget_skipped",
            "max_sources",
        ),
    }.items():
        if isinstance(diagnostics.get(key), dict):
            record[key] = {
                field: diagnostics[key][field] for field in fields if field in diagnostics[key]
            }
    return record
