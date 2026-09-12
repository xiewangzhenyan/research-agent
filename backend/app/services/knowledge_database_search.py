"""Exact pgvector search + per-base Chinese BM25, bounded application-side fusion."""

import asyncio
from time import perf_counter

from app.core.exceptions import BadRequestError
from app.repositories.knowledge_search import KnowledgeSearchRepository
from app.services.knowledge_index import MODEL, embed, overlaps_selected
from app.services.knowledge_search_index import (
    QUERY_PREFIX,
    model_fingerprint,
    query_weights,
    tokenizer_version,
)


def metadata(rows):
    return [
        {
            "id": str(c.id),
            "document_id": str(d.id),
            "knowledge_base_id": str(d.knowledge_base_id),
            "title": d.title,
            "source_kind": d.source_kind,
            "revision": d.revision,
            "collection": name,
            "position": c.position,
            "page": c.page,
            "location": c.location,
            "parse_report": d.parse_report,
            "chunking_config": d.chunking_config,
            "file_version": d.sha256,
            "index_generation": str(d.job_id),
            "content": c.content,
            "url": f"/api/knowledge/documents/{d.id}/download",
        }
        for c, d, name in rows
    ]


async def database_search(db, user_id, base_ids, document_ids, query, config, top_k, stats):
    from app.services.knowledge_enrichment import expand_context, rerank_candidates

    started = perf_counter()
    repo = KnowledgeSearchRepository(db, user_id)
    fingerprint = await asyncio.to_thread(model_fingerprint)
    params = {
        "user_id": user_id,
        "base_ids": base_ids,
        "document_ids": document_ids or [],
        "all_documents": document_ids is None,
        "model": MODEL,
        "fingerprint": fingerprint,
        "tokenizer": tokenizer_version(),
    }
    coverage = await repo.coverage(params)
    stats.update(
        total_chunks=coverage["total"],
        indexed_chunks=coverage["indexed"],
        engine="postgres",
        vector_search="exact",
        tokenizer=params["tokenizer"],
        model_fingerprint=fingerprint,
        keyword_eligible=0,
        semantic_eligible=0,
        keyword_candidates=0,
        semantic_candidates=0,
        merged_candidates=0,
        overlap_removed=0,
        limit_removed=0,
        returned=0,
        embedding_ms=0,
    )
    if coverage["total"] != coverage["indexed"]:
        raise BadRequestError(
            message="所选资料的新检索索引尚未就绪，请重新处理资料或联系管理员完成索引重建"
        )
    branches = {}
    if coverage["total"]:
        if config.mode != "keyword" and (config.mode != "hybrid" or config.semantic_weight > 0):
            tick = perf_counter()
            vector = (await asyncio.to_thread(embed, [QUERY_PREFIX + query]))[0]
            stats["embedding_ms"] = round((perf_counter() - tick) * 1000)
            branches["semantic"] = await repo.semantic(params, vector, config)
        if config.mode != "semantic" and (config.mode != "hybrid" or config.keyword_weight > 0):
            weights = await asyncio.to_thread(query_weights, query)
            branches["keyword"] = await repo.keyword(params, weights, config)
    fused, scores, ranks = {}, {}, {}
    for name, candidates in branches.items():
        stats[name + "_eligible"] = candidates[0]["eligible"] if candidates else 0
        stats[name + "_candidates"] = len(candidates)
        scores[name], ranks[name] = {}, {}
        for rank, candidate in enumerate(candidates, 1):
            key = candidate["chunk_id"]
            scores[name][key], ranks[name][key] = candidate["score"], rank
            contribution = (
                getattr(config, name + "_weight") / (config.rrf_k + rank)
                if config.mode == "hybrid"
                else candidate["score"]
            )
            fused[key] = fused.get(key, 0) + contribution
    stats["merged_candidates"] = len(fused)
    rows = {c["id"]: c for c in metadata(await repo.metadata(params, list(fused)))}
    hits = []
    for key in sorted(fused, key=lambda k: (-fused[k], str(k))):
        chunk = rows.get(str(key))
        if not chunk:
            continue
        if not config.rerank_enabled and overlaps_selected(chunk, hits):
            stats["overlap_removed"] += 1
            continue
        hits.append(
            chunk
            | {
                "score": round(fused[key], 6),
                "index": len(hits) + 1,
                "score_type": {"hybrid": "rrf", "keyword": "bm25", "semantic": "cosine"}[
                    config.mode
                ],
                "retrieval": {
                    "keyword_score": scores.get("keyword", {}).get(key),
                    "semantic_score": scores.get("semantic", {}).get(key),
                    "keyword_rank": ranks.get("keyword", {}).get(key),
                    "semantic_rank": ranks.get("semantic", {}).get(key),
                },
            }
        )
    limit = config.rerank_limit if config.rerank_enabled else top_k
    stats["limit_removed"] = max(0, len(hits) - limit)
    hits = hits[:limit]
    stats["rerank"] = {"status": "disabled", "candidates": 0, "elapsed_ms": 0}
    if config.rerank_enabled:
        hits = await rerank_candidates(query, hits, top_k, stats)
    stats["context"] = {
        "enabled": False,
        "seed_count": len(hits),
        "added": 0,
        "added_chars": 0,
        "budget_skipped": 0,
        "max_sources": 10,
    }
    if config.context_enabled:
        neighbors = metadata(await repo.neighbors(params, hits, config.context_window))
        hits = expand_context(hits, neighbors, config, stats)
    stats["returned"] = len(hits)
    stats["total_ms"] = round((perf_counter() - started) * 1000)
    return hits
