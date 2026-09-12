"""Small synthetic Chinese ordering regression; not a real-document accuracy claim."""

import asyncio
import json
from pathlib import Path

import httpx

from app.core.config import settings
from app.schemas.knowledge import RetrievalConfig
from app.services.knowledge_index import rank_chunks

CASES = [
    (
        "住宿报销上限是多少?",
        [
            "住宿报销申请需填写住宿报销表并附住宿发票。",
            "每人每晚的住宿费最高报销620元。",
            "每日餐费补贴180元。",
        ],
        1,
    ),
    (
        "试用期员工可以申请年假吗?",
        [
            "员工年假申请流程:在系统中填写申请并等待审批。",
            "试用期员工暂不享受年假,转正后方可申请。",
            "正式员工可根据工龄申请五至十五天年假。",
        ],
        1,
    ),
    (
        "2026年差旅补助标准是多少?",
        [
            "2025年差旅补助标准为每天120元。",
            "自2026年1月1日起,差旅补助调整为每天150元。",
            "差旅补助须在出差结束后十日内申请。",
        ],
        1,
    ),
    (
        "设备启动前首先需要做什么?",
        [
            "设备启动完成后观察指示灯。",
            "启动设备前第一步是检查接地和电源连接,确认后再按启动键。",
            "设备停止后断开电源并清洁外壳。",
        ],
        1,
    ),
]


async def main():
    rows = []
    async with httpx.AsyncClient(timeout=45, trust_env=False) as client:
        for query, documents, expected in CASES:
            chunks = [
                {
                    "id": str(i),
                    "document_id": str(i),
                    "position": 0,
                    "content": content,
                    "embedding": [],
                }
                for i, content in enumerate(documents)
            ]
            baseline = rank_chunks(
                query,
                [],
                chunks,
                top_k=10,
                config=RetrievalConfig(mode="keyword"),
                deduplicate=False,
            )
            response = await client.post(
                settings.RAG_RERANK_URL + "/rank",
                json={"query": query, "documents": [c["content"] for c in baseline]},
            )
            response.raise_for_status()
            result = response.json()
            winner = max(range(len(baseline)), key=lambda i: result["scores"][i])
            rows.append(
                {
                    "query": query,
                    "expected_id": str(expected),
                    "baseline_top1": baseline[0]["id"],
                    "reranked_top1": baseline[winner]["id"],
                    "scores": result["scores"],
                    "candidate_ids": [c["id"] for c in baseline],
                    "elapsed_ms": result["inference_ms"],
                }
            )
    report = {
        "synthetic_only": True,
        "cases": rows,
        "baseline_correct": sum(r["baseline_top1"] == r["expected_id"] for r in rows),
        "reranked_correct": sum(r["reranked_top1"] == r["expected_id"] for r in rows),
    }
    Path("/tmp/rerank-evaluation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


asyncio.run(main())
