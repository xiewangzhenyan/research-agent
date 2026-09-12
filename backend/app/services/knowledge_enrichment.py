"""Model reranking and individually attributable neighboring evidence."""

import math
from time import perf_counter

import httpx

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.services.knowledge_index import overlaps_selected

RERANK_MODEL = "BAAI/bge-reranker-base"
RERANK_REVISION = "2cfc18c9415c912f9d8155881c133215df768a70"


async def rerank_candidates(query, candidates, limit, stats):
    started = perf_counter()
    if not candidates:
        stats["rerank"] = {"status": "no_candidates", "candidates": 0, "elapsed_ms": 0}
        return []
    try:
        async with httpx.AsyncClient(timeout=45, trust_env=False) as client:
            response = await client.post(
                settings.RAG_RERANK_URL + "/rank",
                json={"query": query, "documents": [c["content"] for c in candidates]},
            )
        response.raise_for_status()
        result = response.json()
        scores = result["scores"]
        if result["model"] != RERANK_MODEL or result["revision"] != RERANK_REVISION:
            raise ValueError("Unexpected model version")
        if len(scores) != len(candidates) or not all(
            type(x) in {float, int} and math.isfinite(x) for x in scores
        ):
            raise ValueError("Invalid scores")
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise BadRequestError(
            message="本地重排服务忙或暂不可用，请稍后重试，或关闭本地重排后检索"
        ) from exc
    ordered = sorted(range(len(candidates)), key=lambda i: scores[i], reverse=True)
    selected = []
    removed = 0
    for rank, idx in enumerate(ordered, 1):
        candidate = candidates[idx]
        if overlaps_selected(candidate, selected):
            removed += 1
            continue
        selected.append(
            candidate
            | {
                "score": round(scores[idx], 6),
                "score_type": "reranker",
                "retrieval": candidate["retrieval"]
                | {
                    "initial_rank": idx + 1,
                    "initial_score": candidate["score"],
                    "initial_score_type": candidate["score_type"],
                    "rerank_rank": rank,
                    "rerank_model": RERANK_MODEL,
                },
            }
        )
    stats["overlap_removed"] += removed
    stats["limit_removed"] += max(0, len(selected) - limit)
    stats["rerank"] = {
        "status": "applied",
        "model": RERANK_MODEL,
        "revision": RERANK_REVISION,
        "candidates": len(candidates),
        "elapsed_ms": round((perf_counter() - started) * 1000),
        "truncated_pairs": result.get("truncated_pairs", 0),
        "max_tokens": 512,
    }
    selected = selected[:limit]
    for i, hit in enumerate(selected, 1):
        hit["index"] = i
    stats["returned"] = len(selected)
    return selected


def expand_context(seeds, chunks, config, stats):
    """Only use the already-authorized, same-statement index snapshot. Never merge pages."""
    by_position = {(c["document_id"], c["index_generation"], c["position"]): c for c in chunks}
    result = [dict(seed) for seed in seeds]
    seen = {c["id"] for c in seeds}
    added = {}
    chars = 0
    skipped_budget = 0
    for distance in range(1, config.context_window + 1):
        for seed in seeds:
            for offset in (-distance, distance):
                neighbor = by_position.get(
                    (seed["document_id"], seed["index_generation"], seed["position"] + offset)
                )
                if not neighbor:
                    continue
                # Preserve Word section/table boundaries; PDF page boundaries remain
                # independently citable instead of pretending they are one page.
                a, b = seed.get("location") or {}, neighbor.get("location") or {}
                if a.get("section") != b.get("section") or a.get("table") != b.get("table"):
                    continue
                if neighbor["id"] in seen:
                    if neighbor["id"] in added:
                        parents = added[neighbor["id"]]["context_of"]
                        if seed["id"] not in parents:
                            parents.append(seed["id"])
                    continue
                if (
                    len(result) >= 10
                    or chars + len(neighbor["content"]) > config.context_char_budget
                ):
                    skipped_budget += 1
                    continue
                item = {k: v for k, v in neighbor.items() if k != "embedding"} | {
                    "index": len(result) + 1,
                    "score": 0,
                    "score_type": "context",
                    "context_of": [seed["id"]],
                    "retrieval": {
                        "keyword_score": None,
                        "semantic_score": None,
                        "keyword_rank": None,
                        "semantic_rank": None,
                    },
                }
                result.append(item)
                seen.add(item["id"])
                added[item["id"]] = item
                chars += len(item["content"])
    stats["context"] = {
        "enabled": True,
        "seed_count": len(seeds),
        "added": len(added),
        "added_chars": chars,
        "budget_skipped": skipped_budget,
        "max_sources": 10,
    }
    stats["returned"] = len(result)
    return result
