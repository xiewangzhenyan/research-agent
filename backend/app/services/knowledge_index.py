"""Document parsing, local embeddings and BM25/RRF retrieval primitives."""

import csv
import io
import math
import re
import threading
from collections import Counter
from functools import lru_cache
from pathlib import Path
from zipfile import ZipFile

import numpy as np

from app.core.config import settings
from app.schemas.knowledge import RetrievalConfig
from app.services.knowledge_terms import retrieval_aliases

MODEL = "BAAI/bge-small-zh-v1.5"
EMBED_LOCK = threading.Lock()
MAX_CHUNKS_PER_DOCUMENT = 1200


@lru_cache(maxsize=1)
def encoder():
    from fastembed import TextEmbedding

    return TextEmbedding(
        MODEL, cache_dir=str(settings.RAG_MODEL_CACHE), threads=2, local_files_only=True
    )


def embed(texts: list[str]) -> list[list[float]]:
    # Bounded batches, one inference at a time in each process.
    with EMBED_LOCK:
        vectors = list(encoder().embed(texts, batch_size=16))
    return [v.astype(float).tolist() for v in vectors]


def parse_with_report(data: bytes, filename: str) -> tuple[list[dict], dict | None]:
    """Preserve reading order and logical table rows; Word has no stable page numbers."""
    ext = Path(filename).suffix.lower()
    blocks = []
    report = None
    if ext == ".pdf":
        from app.services.knowledge_pdf import extract_pdf

        blocks, report = extract_pdf(data)
    elif ext == ".docx":
        from docx import Document
        from docx.table import Table

        with ZipFile(io.BytesIO(data)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 50 * 1024 * 1024:
                raise ValueError("Word 解压后内容超过 50 MB，请拆分后上传。")
        doc = Document(io.BytesIO(data))
        section, table_number = "", 0
        for element in doc.iter_inner_content():
            if isinstance(element, Table):
                table_number += 1
                rows = [[c.text.strip() for c in row.cells] for row in element.rows]
                blocks.extend(table_blocks(rows, {"section": section, "table": table_number}))
            else:
                if element.style and element.style.name.startswith("Heading"):
                    section = element.text
                location = {"section": section}
                if blocks and not blocks[-1].get("header") and blocks[-1]["location"] == location:
                    blocks[-1]["text"] += "\n" + element.text
                else:
                    blocks.append({"page": None, "text": element.text, "location": location})
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("gb18030")
        if ext == ".csv":
            # csv.reader handles quoted delimiters, escaped quotes and embedded newlines.
            rows = list(csv.reader(io.StringIO(text, newline="")))
            blocks = table_blocks(rows, {"table": 1})
        else:
            blocks = [{"page": None, "text": text, "location": {}}]
    if sum(len(b["text"]) + len(b.get("header", "")) for b in blocks) > 1_000_000:
        raise ValueError("文档文字过多，请拆分后上传。")
    if not any(b["text"].strip() for b in blocks):
        raise ValueError("无法读取文字。扫描 PDF 请先 OCR，再上传包含可复制文字的文件。")
    return blocks, report


def parse_blocks(data: bytes, filename: str) -> list[dict]:
    return parse_with_report(data, filename)[0]


def table_blocks(rows: list[list[str]], location: dict) -> list[dict]:
    if not rows:
        return []
    header = " | ".join(rows[0])
    if len(header) > 200:
        raise ValueError("表头超过 200 字，请精简表头后上传。")
    return [
        {
            "page": None,
            "header": header,
            "text": " | ".join(row),
            "location": location | {"row": i + 1, "kind": "table_row"},
        }
        for i, row in enumerate(rows)
        if (i > 0 or len(rows) == 1) and any(c.strip() for c in row)
    ]


def parse_document(data: bytes, filename: str) -> list[tuple[int | None, str]]:
    """Compatibility API for callers that only need ordered plain text."""
    return [(b["page"], b["text"]) for b in parse_blocks(data, filename)]


def split_blocks(blocks: list[dict], size: int = 450, overlap: int = 65) -> list[dict]:
    if not 0 <= overlap < size:
        raise ValueError("Invalid chunk overlap")
    result = []
    for block in blocks:
        header = block.get("header", "")
        prefix = f"表头：{header}\n" if header else ""
        for part in split_document(
            [(block["page"], block["text"])],
            size=size - len(prefix),
            overlap=0 if header else overlap,
        ):
            result.append(
                part
                | {
                    "position": len(result),
                    "content": prefix + part["content"],
                    "location": block["location"],
                }
            )
            if len(result) > MAX_CHUNKS_PER_DOCUMENT:
                raise ValueError("文档片段过多，请拆分后上传。")
    return result


def split_document(
    pages: list[tuple[int | None, str]], size: int = 450, overlap: int = 65
) -> list[dict]:
    if not 0 <= overlap < size:
        raise ValueError("Invalid chunk overlap")
    result = []
    for page, raw in pages:
        text = re.sub(r"[ \t]+", " ", raw).replace("\x00", "").strip()
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                window = text[start + size // 2 : end]
                boundaries = [window.rfind(sep) for sep in ["\n", "。", "！", "？", ". ", "; "]]
                if max(boundaries) >= 0:
                    end = start + size // 2 + max(boundaries) + 1
            content = text[start:end].strip()
            if content:
                result.append({"position": len(result), "page": page, "content": content})
            if len(result) > MAX_CHUNKS_PER_DOCUMENT:
                raise ValueError("文档片段过多，请拆分后上传。")
            if end == len(text):
                break
            start = max(start + 1, end - overlap)
    return result


def tokens(text: str) -> list[str]:
    result = re.findall(r"[a-z0-9_]+", text.lower())
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        result.extend(run if len(run) == 1 else [run[i : i + 2] for i in range(len(run) - 1)])
    return result


def overlaps_selected(candidate, selected):
    return any(
        x["document_id"] == candidate["document_id"]
        and abs(x["position"] - candidate["position"]) <= 1
        and x.get("page") == candidate.get("page")
        and x.get("location", {}) == candidate.get("location", {})
        and (candidate.get("chunking_config") or {}).get("chunk_overlap", 65) > 0
        and not candidate.get("location", {}).get("row")
        and not x.get("location", {}).get("row")
        for x in selected
    )


def rank_chunks(
    query: str,
    vector: list[float],
    chunks: list[dict],
    top_k: int = 6,
    *,
    expand_terms: bool = True,
    config: RetrievalConfig | None = None,
    diagnostics: dict | None = None,
    deduplicate: bool = True,
) -> list[dict]:
    config = config or RetrievalConfig()
    stats = diagnostics if diagnostics is not None else {}
    stats.update(
        total_chunks=len(chunks),
        keyword_eligible=0,
        semantic_eligible=0,
        keyword_candidates=0,
        semantic_candidates=0,
        merged_candidates=0,
        overlap_removed=0,
        limit_removed=0,
        returned=0,
    )
    if not chunks:
        return []
    lexical = np.zeros(len(chunks))
    if config.mode != "semantic" and (config.mode != "hybrid" or config.keyword_weight > 0):
        counts = [Counter(tokens(c["content"])) for c in chunks]
        lengths = [sum(c.values()) for c in counts]
        average = max(1, sum(lengths) / len(lengths))
        weights = dict.fromkeys(tokens(query), 1.0)
        if expand_terms:
            # Only the lexical branch expands. Preserve the original embedding/query;
            # common words in aliases (e.g. "of" in "limit of detection") add no signal.
            stopwords = {"a", "an", "and", "of", "the", "to", "in", "for", "with", "on"}
            extra = tokens(" ".join(retrieval_aliases(query)))
            for term in dict.fromkeys(extra):
                if term not in stopwords:
                    weights.setdefault(term, 0.35)
        for term, weight in weights.items():
            df = sum(term in c for c in counts)
            idf = math.log(1 + (len(chunks) - df + 0.5) / (df + 0.5))
            for i, counter in enumerate(counts):
                tf = counter[term]
                lexical[i] += (
                    weight * idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * lengths[i] / average))
                )
    semantic = None
    if config.mode != "keyword" and (config.mode != "hybrid" or config.semantic_weight > 0):
        matrix = np.asarray([c["embedding"] for c in chunks], dtype=np.float32)
        q = np.asarray(vector, dtype=np.float32)
        semantic = matrix @ q / np.maximum(np.linalg.norm(matrix, axis=1) * np.linalg.norm(q), 1e-8)
    fused: dict[int, float] = {}
    branch_ranks: dict[str, dict[int, int]] = {"keyword": {}, "semantic": {}}
    branches = []
    if semantic is not None:
        branches.append(("semantic", semantic, config.semantic_threshold, config.semantic_weight))
    if config.mode != "semantic" and (config.mode != "hybrid" or config.keyword_weight > 0):
        branches.append(("keyword", lexical, config.keyword_threshold, config.keyword_weight))
    for name, scores, threshold, weight in branches:
        eligible = [
            int(i)
            for i in np.argsort(-scores, kind="stable")
            if scores[i] >= threshold and (name != "keyword" or scores[i] > 0)
        ]
        stats[name + "_eligible"] = len(eligible)
        candidates = eligible[: config.candidate_limit]
        stats[name + "_candidates"] = len(candidates)
        for rank, idx in enumerate(candidates, 1):
            branch_ranks[name][idx] = rank
            value = (
                weight / (config.rrf_k + rank) if config.mode == "hybrid" else float(scores[idx])
            )
            fused[idx] = fused.get(idx, 0) + value
    stats["merged_candidates"] = len(fused)
    results = []
    for i in sorted(fused, key=fused.get, reverse=True):
        c = chunks[i]
        # Chunk overlap never crosses a parsed page or logical section. Adjacency
        # alone is insufficient: neighboring pages can contain different evidence.
        if deduplicate and overlaps_selected(c, results):
            stats["overlap_removed"] += 1
            continue
        results.append(
            {k: v for k, v in c.items() if k != "embedding"}
            | {
                "score": round(fused[i], 6),
                "score_type": {"hybrid": "rrf", "keyword": "bm25", "semantic": "cosine"}[
                    config.mode
                ],
                "index": len(results) + 1,
                "retrieval": {
                    "keyword_score": round(float(lexical[i]), 6)
                    if config.mode != "semantic"
                    and (config.mode != "hybrid" or config.keyword_weight > 0)
                    else None,
                    "semantic_score": round(float(semantic[i]), 6)
                    if semantic is not None
                    else None,
                    "keyword_rank": branch_ranks["keyword"].get(i),
                    "semantic_rank": branch_ranks["semantic"].get(i),
                },
            }
        )
    stats["limit_removed"] = max(0, len(results) - top_k)
    results = results[:top_k]
    stats["returned"] = len(results)
    return results
