"""Short-lived Linux parsing process; never loads the embedding model."""

import json
import resource
import sys


def main():
    resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    from app.schemas.knowledge import ChunkingConfig
    from app.services.knowledge_index import parse_with_report, split_blocks
    from app.services.knowledge_preview import PREVIEW_ITEMS

    try:
        config = ChunkingConfig(chunk_size=int(sys.argv[2]), chunk_overlap=int(sys.argv[3]))
        raw = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
        if not raw or len(raw) > 10 * 1024 * 1024:
            raise ValueError("文件不能为空，且不能超过 10 MB")
        blocks, report = parse_with_report(raw, sys.argv[1])
        chunks = split_blocks(blocks, size=config.chunk_size, overlap=config.chunk_overlap)
        if not chunks:
            raise ValueError("无法提取有效内容，请检查文件或先完成 OCR。")
        lengths = [len(c["content"]) for c in chunks]
        result = {
            "chunking_config": config.model_dump(),
            "parse_report": report,
            "chunk_count": len(chunks),
            "items": chunks[:PREVIEW_ITEMS],
            "truncated": len(chunks) > PREVIEW_ITEMS,
            "min_length": min(lengths),
            "max_length": max(lengths),
            "mean_length": round(sum(lengths) / len(lengths)),
        }
    except (ValueError, UnicodeError) as exc:
        result = {"error": str(exc)[:300]}
    except Exception:
        result = {"error": "无法解析文件，请检查文件是否损坏、加密或超过资源限制"}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
