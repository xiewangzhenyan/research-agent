"use client";
import { useLocale } from "next-intl";

import { useQuery } from "@tanstack/react-query";
import { knowledgeRequest, type PDFParseReport } from "@/lib/knowledge";
import { ParseReport } from "@/components/knowledge/parse-report";
import { useAuthStore } from "@/stores";
import { evidenceSegments } from "@/lib/evidence-highlight";
import { useEffect, useRef, useState } from "react";
import { FileText, Globe, Link, X } from "lucide-react";
import { useSourcesPanelStore } from "@/stores/sources-panel-store";
import type { SourceItem } from "@/lib/chat-sources";
import { cn } from "@/lib/utils";

function ScoreDot({ score }: { score: number }) {
  const tone =
    score >= 0.7 ? "bg-foreground" : score >= 0.4 ? "bg-foreground/55" : "bg-foreground/25";
  return (
    <span
      className={cn("h-1.5 w-1.5 shrink-0 rounded-full", tone)}
      title={`Relevance: ${score.toFixed(2)}`}
    />
  );
}

function RAGSourceRow({ item, highlighted }: { item: SourceItem; highlighted: boolean }) {
  const zh = useLocale() === "zh";
  const userId = useAuthStore((s) => s.user?.id);
  const [showContext, setShowContext] = useState(false);
  const { data, isPending, isError } = useQuery({
    queryKey: ["knowledge-citation", userId, item.citationId],
    queryFn: () => knowledgeRequest<{ state: string; title: string; content: string; quotes?: string[]; file_version?: string; location?: { section?: string; table?: number; row?: number }; url?: string; preview_url?: string; parse_report?: PDFParseReport | null }>(`citations/${item.citationId}`),
    enabled: !!item.citationId && !!userId,
    staleTime: 0,
    gcTime: 0,
    retry: 1,
    refetchInterval: 15000,
  });
  const context = useQuery({
    queryKey: ["knowledge-citation-context", userId, item.citationId],
    queryFn: () => knowledgeRequest<{ state: string; items: Array<{ id: string; page: number | null; position: number; content: string; cited: boolean }> }>(`citations/${item.citationId}/context`),
    enabled: !!item.citationId && !!userId && showContext && data?.state === "current",
    staleTime: 0,
    gcTime: 0,
    retry: 1,
    refetchInterval: 15000,
  });
  const content = item.citationId ? (isError ? "引用暂时无法读取，请稍后重试。" : isPending ? "正在读取原文依据…" : data?.state === "deleted" ? "原文已删除，引用内容已清除。" : data?.content) : item.content;
  const download = item.citationId ? data?.url : item.url;
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (highlighted) {
      ref.current?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
        block: "nearest",
      });
    }
  }, [highlighted]);

  return (
    <div
      ref={ref}
      className={cn(
        "border-foreground/8 rounded-xl border p-3 transition-colors",
        highlighted && "border-foreground/30 bg-foreground/[0.04]",
      )}
    >
      <div className="flex items-start gap-2.5">
        <span className="bg-foreground/8 text-foreground/65 mt-0.5 inline-flex h-5 min-w-[1.5rem] shrink-0 items-center justify-center rounded px-1 font-mono text-[10px] tabular-nums">
          {item.index}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <FileText className="text-foreground/40 h-3.5 w-3.5 shrink-0" />
            <p className="text-foreground truncate text-xs font-medium" title={item.title}>
              {item.title}
            </p>
            {item.score !== undefined && <ScoreDot score={item.score} />}
          </div>
          {item.subtitle && (
            <p className="text-foreground/45 mt-0.5 pl-5 font-mono text-[10px] tracking-wider uppercase">
              {zh ? item.subtitle.replace(/\bchunk (\d+)/g, "片段 $1").replace(/\bp\.(\d+)/g, "第 $1 页") : item.subtitle}
            </p>
          )}
          {download && item.type === "rag" && (
            <a
              href={download}
              className="text-brand mt-2 inline-block text-xs underline underline-offset-4"
            >
              下载原文
            </a>
          )}
          {data?.preview_url && <a href={data.preview_url} target="_blank" rel="noopener noreferrer" className="text-brand ml-3 text-xs underline">打开引用页</a>}
          {data?.file_version && <p className="text-muted-foreground mt-2 text-xs">文件版本 {data.file_version.slice(0, 12)}{data.state === "reindexed" ? " · 索引已更新，以下为回答时的片段" : " · 回答时的原文片段"}</p>}
          {data?.parse_report && data.state !== "deleted" && <ParseReport report={data.parse_report} snapshot />}
          {data?.location && <p className="text-muted-foreground mt-2 text-xs">{[data.location.section, data.location.table && `表 ${data.location.table}`, data.location.row && `第 ${data.location.row} 行`].filter(Boolean).join(" · ")}</p>}
          {!!data?.quotes?.length && data.state !== "deleted" && <p className="text-brand mt-3 text-xs">高亮为本次回答采用的原句</p>}
          {content && (
            <p className="text-foreground/60 mt-2 pl-5 text-sm leading-7 whitespace-pre-wrap">
              {evidenceSegments(content, data?.quotes).map((part, i) => part.highlighted ? <mark key={i} className="rounded-sm bg-emerald-300/15 px-0.5 text-emerald-200">{part.text}</mark> : <span key={i}>{part.text}</span>)}
            </p>
          )}
          {item.citationId && data?.state === "current" && <div className="mt-3 pl-5">
            <button type="button" className="text-brand text-xs underline underline-offset-4" onClick={() => setShowContext(!showContext)}>{showContext ? "收起上下文" : "展开前后文"}</button>
            {showContext && <div className="mt-3 space-y-3">
              {context.isPending && <p className="text-muted-foreground text-xs">正在读取上下文…</p>}
              {context.isError && <p role="alert" className="text-muted-foreground text-xs">上下文读取失败，请重试。</p>}
              {context.data?.state !== "current" && context.isSuccess && <p className="text-muted-foreground text-xs">原文已变化，保留上方回答时的引用片段。</p>}
              {context.data?.state === "current" && context.data.items.map((passage) => <div key={passage.id} className="rounded-lg border p-3">
                <p className="text-muted-foreground text-xs">{passage.cited ? "引用所在片段" : "相邻片段"} · {passage.page ? `第 ${passage.page} 页 · ` : ""}片段 {passage.position + 1}</p>
                <p className="mt-2 text-sm leading-7 whitespace-pre-wrap">{passage.content}</p>
              </div>)}
            </div>}
          </div>}

        </div>
      </div>
    </div>
  );
}

function WebSourceRow({ item, highlighted }: { item: SourceItem; highlighted: boolean }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (highlighted) {
      ref.current?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
        block: "nearest",
      });
    }
  }, [highlighted]);

  const inner = (
    <div
      ref={ref}
      className={cn(
        "border-foreground/8 rounded-xl border p-3 transition-colors",
        highlighted && "border-foreground/30 bg-foreground/[0.04]",
        item.url && "hover:border-foreground/25 cursor-pointer",
      )}
    >
      <div className="flex items-start gap-2.5">
        <Globe className="text-foreground/40 mt-0.5 h-3.5 w-3.5 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-foreground truncate text-xs font-medium" title={item.title}>
            {item.title}
          </p>
          {item.subtitle && (
            <div className="text-foreground/45 mt-0.5 flex items-center gap-1 text-[10px]">
              <Link className="h-2.5 w-2.5 shrink-0" />
              {item.subtitle}
            </div>
          )}
          {item.url && item.type === "rag" && (
            <a
              href={item.url}
              className="text-brand mt-2 inline-block text-xs underline underline-offset-4"
            >
              下载原文
            </a>
          )}
          {item.content && (
            <p className="text-foreground/60 mt-2 line-clamp-3 text-sm leading-7 whitespace-pre-wrap">
              {item.content}
            </p>
          )}
        </div>
      </div>
    </div>
  );

  if (item.url) {
    return (
      <a href={item.url} target="_blank" rel="noopener noreferrer">
        {inner}
      </a>
    );
  }
  return inner;
}

export function SourcesPanel() {
  const { isOpen, sources, highlightedIndex, close } = useSourcesPanelStore();

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, close]);

  if (!isOpen) return null;

  const ragSources = sources.filter((s) => s.type === "rag");
  const webSources = sources.filter((s) => s.type === "web");

  return (
    <div className="bg-background border-border fixed top-0 right-0 z-50 flex h-full w-[min(420px,100vw)] flex-col border-l shadow-xl">
      {/* Header */}
      <div className="border-foreground/8 flex items-center justify-between border-b px-4 py-3">
        <h2 className="text-foreground text-sm font-semibold">
          原文依据
          <span className="text-foreground/45 ml-2 font-normal">({sources.length})</span>
        </h2>
        <button
          type="button"
          onClick={close}
          aria-label="关闭原文依据"
          className="text-foreground/50 hover:text-foreground hover:bg-foreground/8 rounded-md p-1 transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 space-y-5 overflow-y-auto px-4 py-4">
        {ragSources.length > 0 && (
          <section className="space-y-2">
            {ragSources.length > 0 && webSources.length > 0 && (
              <h3 className="text-foreground/45 font-mono text-[10px] tracking-wider uppercase">
                知识库
              </h3>
            )}
            {ragSources.map((s) => (
              <RAGSourceRow
                key={`rag-${s.index}`}
                item={s}
                highlighted={s.index === highlightedIndex}
              />
            ))}
          </section>
        )}

        {webSources.length > 0 && (
          <section className="space-y-2">
            {ragSources.length > 0 && (
              <h3 className="text-foreground/45 font-mono text-[10px] tracking-wider uppercase">
                网络来源
              </h3>
            )}
            {webSources.map((s) => (
              <WebSourceRow
                key={`web-${s.index}`}
                item={s}
                highlighted={s.index === highlightedIndex}
              />
            ))}
          </section>
        )}
      </div>
    </div>
  );
}
