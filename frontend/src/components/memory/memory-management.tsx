"use client";

import { useState } from "react";
import { useLocale } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Sparkles, History } from "lucide-react";
import {
  Button,
  Switch,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui";
import { apiClient } from "@/lib/api-client";
import { useGenerationConfig } from "@/hooks/use-generation-config";
import {
  memoryError,
  memoryKey,
  type MemoryList,
  type MemoryProposal,
  type MemoryItem,
  type MemorySettings,
} from "@/lib/memory";
import { MemoryEditor } from "./memory-editor";

export function MemoryManagement({
  data,
  refresh,
}: {
  data: MemoryList;
  refresh: () => Promise<unknown>;
}) {
  const zh = useLocale() === "zh";
  const t = (cn: string, en: string) => (zh ? cn : en);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [review, setReview] = useState<MemoryProposal | null>(null);
  const models = useGenerationConfig(data.enabled);
  async function perform(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError(memoryError(e, zh));
    } finally {
      await refresh();
      setBusy(false);
    }
  }
  const setting = (change: Partial<MemorySettings>) =>
    perform(() =>
      apiClient.put("/memory/settings", {
        enabled: data.enabled,
        revision: data.revision,
        ...change,
      }),
    );
  const jobs = data.jobs ?? [];
  const labels: Record<string, string> = {
    queued: t("排队中", "Queued"),
    running: t("正在整理", "Extracting"),
    completed: t("已完成", "Completed"),
    failed: t("未完成", "Failed"),
    cancelled: t("已取消", "Cancelled"),
    skipped: t("已跳过", "Skipped"),
  };
  return (
    <section className="bg-card space-y-5 rounded-2xl border p-5">
      <div className="flex items-start justify-between gap-5">
        <div>
          <label htmlFor="memory-extract" className="flex items-center gap-2 font-medium">
            <Sparkles size={18} className="text-brand" />
            {t("自动整理候选记忆", "Suggest memories from new messages")}
          </label>
          <p className="text-muted-foreground mt-2 max-w-2xl text-sm leading-relaxed">
            {t(
              "开启后，将新用户消息交给下方模型提取长期有用的信息，可能产生模型费用。不补扫历史，不直接写入或覆盖记忆。",
              "Send new user messages to the selected model to suggest useful memories. Model usage may incur costs. No history backfill or automatic overwrites.",
            )}
          </p>
        </div>
        <Switch
          id="memory-extract"
          checked={data.auto_extract ?? false}
          disabled={!data.enabled || busy}
          onCheckedChange={(value) => setting({ auto_extract: value })}
        />
      </div>
      {data.enabled && (
        <div className="grid gap-5 border-t pt-5 sm:grid-cols-2">
          <div>
            <label htmlFor="memory-model" className="text-sm font-medium">
              {t("记忆提取模型", "Extraction model")}
            </label>
            <select
              id="memory-model"
              value={data.extraction_model ?? models.data?.default ?? ""}
              disabled={busy || !models.data}
              onChange={(e) => setting({ extraction_model: e.target.value })}
              className="bg-background mt-2 h-10 w-full min-w-0 rounded-lg border px-3 text-sm"
            >
              {!models.data && <option>{t("正在加载模型…", "Loading models…")}</option>}
              {models.data && !models.data.models.some((m) => m.id === data.extraction_model) && (
                <option value={data.extraction_model}>{data.extraction_model}</option>
              )}
              {models.data?.models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.id}
                </option>
              ))}
            </select>
            {models.isError && (
              <button
                onClick={() => models.refetch()}
                className="text-destructive mt-2 text-xs underline"
              >
                {t("模型加载失败，点击重试", "Model list unavailable. Retry")}
              </button>
            )}
            <p className="text-muted-foreground mt-2 text-xs">
              {t(
                `账号近 24 小时已提取排队 ${data.daily_jobs ?? 0}/${data.daily_limit ?? 20} 次；每条消息最多 5 条建议。`,
                `${data.daily_jobs ?? 0}/${data.daily_limit ?? 20} jobs queued in the last 24 hours for this account; up to 5 suggestions each.`,
              )}
            </p>
          </div>
          <div>
            <div className="flex items-center justify-between gap-3">
              <label htmlFor="memory-semantic" className="text-sm font-medium">
                {t("语义与关键词混合召回", "Semantic and keyword recall")}
              </label>
              <Switch
                id="memory-semantic"
                checked={data.semantic_recall ?? true}
                disabled={busy}
                onCheckedChange={(value) => setting({ semantic_recall: value })}
              />
            </div>
            <p className="text-muted-foreground mt-2 text-xs leading-relaxed">
              {t(
                "使用本地 BGE 中文向量模型。索引准备期间或模型不可用时使用关键词召回。",
                "Uses the local Chinese BGE encoder. Falls back to keywords while indexing or if unavailable.",
              )}
            </p>
            <Button
              size="sm"
              variant="outline"
              className="mt-3"
              disabled={busy || !data.semantic_recall}
              onClick={() => perform(() => apiClient.post("/memory/reindex", {}))}
            >
              {t("重建记忆索引", "Rebuild memory index")}
            </Button>
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}
      <div className="border-t pt-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-medium">
            {t("待确认建议", "Suggestions to review")}{" "}
            <span className="text-muted-foreground text-sm">{data.proposals?.length ?? 0}/20</span>
          </h2>
          <p className="text-muted-foreground text-xs">
            {t(
              "7 天内确认；逾期自动移出候选列表",
              "Review within 7 days; expired suggestions are hidden",
            )}
          </p>
        </div>
        {!data.proposals?.length ? (
          <p className="text-muted-foreground mt-3 text-sm">
            {t(
              "暂无建议。开启后，助手会从后续新消息中整理值得保留的信息。",
              "No suggestions yet. After enabling, useful information from new messages appears here.",
            )}
          </p>
        ) : (
          <div className="mt-4 space-y-3">
            {data.proposals.map((p) => (
              <article key={p.id} className="bg-muted/20 min-w-0 space-y-3 rounded-xl border p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-brand text-xs">
                    {p.action === "update" ? t("更新建议", "Update") : t("新增建议", "New")}
                  </span>
                  <h3 className="text-sm font-medium break-words">{p.payload.title}</h3>
                </div>
                <p className="text-sm break-words whitespace-pre-wrap">{p.payload.content}</p>
                <blockquote className="text-muted-foreground border-l-2 pl-3 text-xs leading-relaxed break-words whitespace-pre-wrap">
                  {t("原文：", "Source: ")}
                  {p.quote}
                </blockquote>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" disabled={busy} onClick={() => setReview(p)}>
                    {t("核对并确认", "Review and confirm")}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    onClick={() =>
                      perform(() =>
                        apiClient.post(`/memory/proposals/${p.id}/reject`, {
                          revision: p.revision,
                        }),
                      )
                    }
                  >
                    {t("忽略建议", "Dismiss")}
                  </Button>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
      {!!jobs.length && (
        <details className="border-t pt-4">
          <summary className="cursor-pointer text-sm">
            {t("最近整理记录", "Recent extraction jobs")}
          </summary>
          <div className="mt-3 space-y-3">
            {jobs.map((j) => (
              <div
                key={j.id}
                className="flex flex-wrap items-start justify-between gap-2 rounded-lg border p-3 text-xs"
              >
                <div className="min-w-0 space-y-1">
                  <p>
                    {labels[j.status] ?? j.status} ·{" "}
                    {new Date(j.created_at).toLocaleString(zh ? "zh-CN" : "en-US")}
                    {j.status === "completed" &&
                      ` · ${j.result_count} ${t("条建议", "suggestions")}`}
                  </p>
                  <p className="text-muted-foreground break-all">
                    {j.model}
                    {j.usage && ` · ${j.usage.input_tokens + j.usage.output_tokens} tokens`}
                  </p>
                  {j.error && (
                    <p className="text-muted-foreground">
                      {zh ? j.error : "Check model settings or review the queue limits."}
                    </p>
                  )}
                </div>
                {j.status === "failed" && j.attempts < 2 && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy || !data.auto_extract || !data.enabled}
                    onClick={() => perform(() => apiClient.post(`/memory/jobs/${j.id}/retry`, {}))}
                  >
                    {t("重试一次", "Retry once")}
                  </Button>
                )}
              </div>
            ))}
          </div>
        </details>
      )}
      {review && (
        <MemoryEditor
          proposal={review}
          onClose={() => {
            setReview(null);
            void refresh();
          }}
        />
      )}
    </section>
  );
}

export function MemoryHistory({ item }: { item: MemoryItem }) {
  const zh = useLocale() === "zh";
  const [open, setOpen] = useState(false);
  const history = useQuery({
    queryKey: [...memoryKey(), "history", item.id, item.revision],
    queryFn: () =>
      apiClient.get<{ items: { revision: number; snapshot: MemoryItem; created_at: string }[] }>(
        `/memory/${item.id}/history`,
      ),
    enabled: open,
  });
  return (
    <>
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        <History size={14} className="mr-1" />
        {zh ? "版本" : "History"}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>{zh ? "记忆版本记录" : "Memory history"}</DialogTitle>
            <DialogDescription>
              {zh
                ? "保留最近 30 个版本。删除来源消息会清除对应版本；删除记忆会清除全部版本。"
                : "Latest 30 versions. Deleting a source removes its versions; deleting the note removes all versions."}
            </DialogDescription>
          </DialogHeader>
          {history.isPending && <p>{zh ? "正在加载…" : "Loading…"}</p>}
          {history.isError && (
            <Button variant="outline" onClick={() => history.refetch()}>
              {zh ? "加载失败，重试" : "Retry loading"}
            </Button>
          )}
          {history.data?.items.map((v) => (
            <article key={v.revision} className="space-y-2 rounded-xl border p-4">
              <p className="text-muted-foreground text-xs">
                v{v.revision} · {new Date(v.created_at).toLocaleString(zh ? "zh-CN" : "en-US")}
              </p>
              <p className="font-medium break-words">{v.snapshot.title}</p>
              <p className="text-sm break-words whitespace-pre-wrap">{v.snapshot.content}</p>
              <p className="text-muted-foreground text-xs">
                {v.snapshot.archived_at
                  ? zh
                    ? "已归档"
                    : "Archived"
                  : zh
                    ? "未归档"
                    : "Not archived"}{" "}
                · {v.snapshot.expires_on ?? (zh ? "无截止日期" : "No expiry")}
              </p>
            </article>
          ))}
        </DialogContent>
      </Dialog>
    </>
  );
}
