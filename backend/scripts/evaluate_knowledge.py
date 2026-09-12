"""Run: python scripts/evaluate_knowledge.py [--answers] [--output report.json].

Synthetic regression benchmark, not a production quality estimate. --answers
runs the configured generation model too; default measures retrieval and rewrite.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

from app.services.knowledge_answer import grounded_answer, rewrite_query
from app.services.knowledge_index import MODEL, embed, rank_chunks, split_blocks
from app.services.knowledge_terms import TERMINOLOGY_VERSION, retrieval_aliases


async def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--answers", action="store_true")
    parser.add_argument("--no-expansion", action="store_true", help="Original lexical baseline")
    parser.add_argument("--output", default="/tmp/knowledge-eval-report.json")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "evals/knowledge_synthetic_v1.json",
    )
    args = parser.parse_args()
    fixture = json.loads(args.dataset.read_text())
    corpus = []
    for doc in fixture["documents"]:
        corpus.extend(
            c | {"document_id": doc["id"], "title": doc["title"]}
            for c in split_blocks(
                doc.get("blocks") or [{"page": None, "text": doc["content"], "location": {}}]
            )
        )
    for chunk, vector in zip(
        corpus, await asyncio.to_thread(embed, [c["content"] for c in corpus]), strict=True
    ):
        chunk["embedding"] = vector
    results = []
    for case in fixture["cases"]:
        started = time.monotonic()
        query, strategy = await rewrite_query(case["question"], case.get("history", []), None)
        vector = (
            await asyncio.to_thread(embed, ["为这个句子生成表示以用于检索相关文章：" + query])
        )[0]
        candidates = [
            c
            for c in corpus
            if not case.get("document_ids") or c["document_id"] in case["document_ids"]
        ]
        hits = rank_chunks(query, vector, candidates, top_k=10, expand_terms=not args.no_expansion)
        row = {
            "id": case["id"],
            "split": case["split"],
            "query_strategy": strategy,
            "query": query,
            "aliases": [] if args.no_expansion else retrieval_aliases(query),
            "expected": case["expected_document"],
            "hits": [h["document_id"] for h in hits],
            "evidence_hits": [{"document_id": h["document_id"], "page": h["page"]} for h in hits],
            "retrieval_ms": round((time.monotonic() - started) * 1000),
        }
        if case.get("expected_evidence"):
            row["expected_evidence"] = case["expected_evidence"]
            row["all_evidence_at_6"] = all(
                e in row["evidence_hits"][:6] for e in case["expected_evidence"]
            )
        if args.answers:
            output, citations, meta = await grounded_answer(
                case["question"], hits[:6], None, resolved_query=query
            )
            row.update(output=output, citations=[c["document_id"] for c in citations], **meta)
            if case.get("expected_evidence"):
                cited_pages = [
                    {"document_id": c["document_id"], "page": c["page"]} for c in citations
                ]
                row["cited_evidence"] = cited_pages
                row["all_evidence_cited"] = all(e in cited_pages for e in case["expected_evidence"])
        results.append(row)
        print(case["id"], "done", flush=True)
    summary = {}
    for split in ["development", "holdout"]:
        subset = [r for r in results if r["split"] == split]
        known = [r for r in subset if r["expected"]]
        unknown = [r for r in subset if not r["expected"]]
        evidence_cases = [r for r in subset if "expected_evidence" in r]
        summary[split] = {
            "known_cases": len(known),
            "unknown_cases": len(unknown),
            **{
                f"recall_at_{k}": sum(r["expected"] in r["hits"][:k] for r in known) / len(known)
                if known
                else None
                for k in [1, 6, 10]
            },
            "unknown_with_candidates": sum(bool(r["hits"]) for r in unknown),
            "no_answer_accuracy": sum(not r.get("citations") for r in unknown) / len(unknown)
            if args.answers and unknown
            else None,
            "citation_support_accuracy": None,
            "all_evidence_recall_at_6": sum(r["all_evidence_at_6"] for r in evidence_cases)
            / len(evidence_cases)
            if evidence_cases
            else None,
        }  # Semantic support requires human claim-by-claim review.
    report = {
        "dataset": args.dataset.stem,
        "model": MODEL,
        "terminology": None if args.no_expansion else TERMINOLOGY_VERSION,
        "generation_evaluated": args.answers,
        "limitations": "Small synthetic corpus; recall is document-level. Citation entailment requires human review. Unknown queries may retrieve related but insufficient passages.",
        "summary": summary,
        "cases": results,
    }
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
