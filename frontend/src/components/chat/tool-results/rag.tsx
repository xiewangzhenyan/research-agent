"use client";
import { useState } from "react";
import { ChevronDown, FileText, Search } from "lucide-react";
import { cn } from "@/lib/utils";

const retrievalLabels = new Map([["rrf", "混合检索"], ["bm25", "关键词检索"], ["cosine", "语义检索"], ["reranker", "本地重排"], ["context", "补充上下文"]]);

interface RAGResultItem {
  index: number;
  source: string;
  url?: string;
  scoreType?: string;
  citationId?: string;
  page?: string;
  chunk?: string;
  collection?: string;
  score: string;
  content: string;
}

export function parseRAGResults(result: string): RAGResultItem[] {
  const items: RAGResultItem[] = [];
  try {
    const payload = JSON.parse(result);
    if (Array.isArray(payload.items))
      return payload.items
        .filter((item: Record<string, unknown>) => typeof item.content === "string")
        .map((item: Record<string, unknown>, i: number) => ({
          index: Number(item.index || i + 1),
          source: String(item.title || "文档"),
          page: item.page ? String(item.page) : undefined,
          chunk: String(Number(item.position || 0) + 1),
          collection: String(item.collection || ""),
          score: String(item.score || 0),
          scoreType: String(item.score_type || ""),
          content: item.citation_id ? "点击回答中的引用编号查看原文依据" : String(item.content),
          citationId: typeof item.citation_id === "string" && /^[a-f0-9-]{36}$/.test(item.citation_id) ? item.citation_id : undefined,
          url:
            typeof item.url === "string" &&
            /^\/api\/knowledge\/documents\/[a-f0-9-]+\/download$/.test(item.url)
              ? item.url
              : undefined,
        }));
  } catch {
    /* Previous conversations use the text format below. */
  }

  // Match: [1] Source: filename, page X, chunk Y [collection] (score: 0.xxx)\ncontent
  const pattern =
    /\[(\d+)\]\s*Source:\s*([^,\n]+?)(?:,\s*page\s*(\d+))?(?:,\s*chunk\s*(\d+))?(?:\s*\[([^\]]+)\])?\s*\(score:\s*([\d.]+)\)\n([\s\S]*?)(?=\n\[\d+\]|$)/g;
  let match;
  while ((match = pattern.exec(result)) !== null) {
    items.push({
      index: parseInt(match[1] ?? "0"),
      source: (match[2] ?? "").trim(),
      page: match[3],
      chunk: match[4],
      collection: match[5],
      score: match[6] ?? "",
      content: (match[7] ?? "").trim(),
    });
  }
  return items;
}

export function RAGSearchResults({ result }: { result: string }) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const items = parseRAGResults(result);

  if (items.length === 0) {
    if (result.includes("No relevant documents")) {
      return (
        <div className="text-muted-foreground flex items-center gap-2 py-2 text-sm">
          <Search className="h-4 w-4" />
          No relevant documents found
        </div>
      );
    }
    return null; // fallback to default renderer
  }

  // Group chunks by source filename so the same file doesn't render as N
  // duplicate cards. Preserve insertion order so the indices stay readable.
  const grouped = items.reduce<Map<string, RAGResultItem[]>>((acc, item) => {
    const key = item.source || "Unknown";
    const list = acc.get(key) ?? [];
    list.push(item);
    acc.set(key, list);
    return acc;
  }, new Map());
  const sourceCount = grouped.size;

  return (
    <div className="space-y-3 py-1">
      <div className="text-foreground/55 flex items-center gap-2 font-mono text-[10px] tracking-wider uppercase">
        <Search className="h-3 w-3" />
        <span>
          {items.length} chunk{items.length !== 1 ? "s" : ""}
        </span>
        <span>·</span>
        <span>
          {sourceCount} source{sourceCount !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="border-foreground/10 divide-foreground/8 divide-y overflow-hidden rounded-xl border">
        {Array.from(grouped.entries()).map(([source, chunks]) => (
          <RAGSourceGroup
            key={source}
            source={source}
            chunks={chunks}
            expandedIdx={expandedIdx}
            onToggle={(idx) => setExpandedIdx(expandedIdx === idx ? null : idx)}
          />
        ))}
      </div>
    </div>
  );
}

function RAGSourceGroup({
  source,
  chunks,
  expandedIdx,
  onToggle,
}: {
  source: string;
  url?: string;
  scoreType?: string;
  chunks: RAGResultItem[];
  expandedIdx: number | null;
  onToggle: (idx: number) => void;
}) {
  const collection = chunks[0]?.collection;
  const bestScore = Math.max(...chunks.map((c) => parseFloat(c.score) || 0));
  return (
    <div>
      <div className="bg-foreground/[0.02] flex items-center gap-2 px-3 py-2">
        <FileText className="text-foreground/55 h-3.5 w-3.5 shrink-0" />
        <span className="text-foreground truncate text-xs font-medium" title={source}>
          {source}
        </span>
        <span className="text-foreground/45 ml-auto font-mono text-[10px] tracking-wider uppercase">
          {chunks.length} chunk{chunks.length !== 1 ? "s" : ""}
        </span>
        {!["rrf", "bm25", "cosine", "reranker", "context"].includes(chunks[0]?.scoreType || "") && <ScoreDot score={bestScore} />}
        {collection && (
          <span
            className="border-foreground/15 text-foreground/55 hidden shrink-0 rounded-full border px-1.5 py-0.5 font-mono text-[9px] tracking-wider uppercase sm:inline"
            title={`Collection: ${collection}`}
          >
            {collection}
          </span>
        )}
      </div>
      <ul>
        {chunks.map((chunk) => {
          const isOpen = expandedIdx === chunk.index;
          return (
            <li key={chunk.index} className="border-foreground/8 border-t first:border-t-0">
              <button
                type="button"
                onClick={() => onToggle(chunk.index)}
                className="hover:bg-foreground/[0.02] flex w-full items-start gap-2.5 px-3 py-2 text-left transition-colors"
              >
                <span className="bg-foreground/8 text-foreground/65 mt-0.5 inline-flex h-5 min-w-[1.5rem] shrink-0 items-center justify-center rounded px-1 font-mono text-[10px] tabular-nums">
                  {chunk.index}
                </span>
                <div className="min-w-0 flex-1">
                  <p
                    className={cn(
                      "text-foreground/80 text-xs leading-relaxed",
                      !isOpen && "line-clamp-2",
                    )}
                  >
                    {chunk.content}
                  </p>
                  {(chunk.page || chunk.chunk) && (
                    <div className="text-foreground/45 mt-1 flex items-center gap-1.5 font-mono text-[10px] tracking-wider uppercase">
                      {chunk.page && <span>p.{chunk.page}</span>}
                      {chunk.chunk && (
                        <>
                          {chunk.page && <span>·</span>}
                          <span>chunk {chunk.chunk}</span>
                        </>
                      )}
                    </div>
                  )}
                </div>
                <div className="mt-0.5 flex shrink-0 items-center gap-1.5">
                  <span className="text-foreground/55 font-mono text-[10px] tabular-nums">
                    {(retrievalLabels.get(chunk.scoreType || "") || parseFloat(chunk.score).toFixed(2))}
                  </span>
                  {!["rrf", "bm25", "cosine", "reranker", "context"].includes(chunk.scoreType || "") && <ScoreDot score={parseFloat(chunk.score) || 0} />}
                  <ChevronDown
                    className={cn(
                      "text-foreground/40 h-3.5 w-3.5 transition-transform",
                      isOpen && "rotate-180",
                    )}
                  />
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Tiny dot indicating chunk relevance — neutral palette, no warning colors. */
function ScoreDot({ score }: { score: number }) {
  // Map score to brand-tone opacity instead of red/yellow/green so the UI
  // reads as a quality signal, not an alert.
  const tone =
    score >= 0.7 ? "bg-foreground" : score >= 0.4 ? "bg-foreground/55" : "bg-foreground/25";
  return (
    <span
      className={cn("h-1.5 w-1.5 shrink-0 rounded-full", tone)}
      title={`Relevance: ${score.toFixed(2)}`}
    />
  );
}
