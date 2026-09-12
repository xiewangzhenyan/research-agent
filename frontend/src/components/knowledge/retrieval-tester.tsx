"use client";

import { useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";
import { Button, Input } from "@/components/ui";
import {
  knowledgeRequest as api,
  DEFAULT_RETRIEVAL_CONFIG,
  type KnowledgeBase,
  type RetrievalConfig,
  type RetrievalResult,
} from "@/lib/knowledge";

const modes = [
  { value: "hybrid", label: "混合检索", description: "结合关键词与语义，适合多数问题" },
  { value: "keyword", label: "关键词检索", description: "查找名称、编号或明确用词" },
  { value: "semantic", label: "语义检索", description: "按含义查找，适合不同表述" },
] as const;
const fields = [
  {
    key: "result_limit",
    label: "返回片段数",
    min: 1,
    max: 10,
    step: 1,
    hint: "核心命中数量；补充上下文后总计最多 10 段",
  },
  {
    key: "candidate_limit",
    label: "每路候选数",
    min: 10,
    max: 100,
    step: 1,
    hint: "进入合并排序前，每路最多保留的片段数",
  },
  {
    key: "semantic_threshold",
    label: "语义相似度下限",
    min: 0,
    max: 1,
    step: 0.01,
    hint: "0–1；提高下限会减少语义候选",
  },
  {
    key: "keyword_threshold",
    label: "关键词得分下限",
    min: 0,
    max: 100,
    step: 0.1,
    hint: "BM25 得分；0 表示保留所有正向匹配",
  },
  {
    key: "semantic_weight",
    label: "语义排序权重",
    min: 0,
    max: 2,
    step: 0.1,
    hint: "仅混合模式使用，0 表示关闭该路",
  },
  {
    key: "keyword_weight",
    label: "关键词排序权重",
    min: 0,
    max: 2,
    step: 0.1,
    hint: "仅混合模式使用，0 表示关闭该路",
  },
  {
    key: "rrf_k",
    label: "排名平滑值（RRF）",
    min: 10,
    max: 100,
    step: 1,
    hint: "仅混合模式使用；较大值减弱名次差异",
  },
  {
    key: "rerank_limit",
    label: "重排候选数",
    min: 10,
    max: 20,
    step: 1,
    hint: "更多候选需要更长计算时间",
  },
  {
    key: "context_window",
    label: "前后扩展范围",
    min: 1,
    max: 2,
    step: 1,
    hint: "每个核心命中向前、向后查找的片段数",
  },
  {
    key: "context_char_budget",
    label: "补充上下文字数上限",
    min: 500,
    max: 2000,
    step: 100,
    hint: "只计算额外片段，保留完整原文块",
  },
] as const;

export function RetrievalTester({ base, readyCount }: { base: KnowledgeBase; readyCount: number }) {
  const id = useId();
  const form = useRef<HTMLFormElement>(null);
  const request = useRef<AbortController | null>(null);
  const [saved, setSaved] = useState<RetrievalConfig | null>(null);
  const [config, setConfig] = useState<RetrievalConfig>(DEFAULT_RETRIEVAL_CONFIG);
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<RetrievalResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api<RetrievalConfig>("retrieval-config", { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) {
          setSaved(data);
          setConfig(data);
          setError("");
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "设置加载失败");
      });
    return () => {
      controller.abort();
      request.current?.abort();
    };
  }, [reload]);
  function invalidate() {
    request.current?.abort();
    setBusy(false);
    setResult(null);
    setError("");
  }
  function edit(next: RetrievalConfig) {
    invalidate();
    setConfig(next);
  }
  function valid() {
    if (!form.current?.checkValidity()) {
      const details = form.current?.closest("details");
      if (details) details.open = true;
      form.current?.reportValidity();
      return false;
    }
    if (config.mode === "hybrid" && config.semantic_weight + config.keyword_weight === 0) {
      setError("混合检索至少需要一个大于零的权重");
      return false;
    }
    return true;
  }
  async function run(event: React.FormEvent) {
    event.preventDefault();
    if (!saved || !query.trim() || !valid()) return;
    invalidate();
    setBusy(true);
    const controller = new AbortController();
    request.current = controller;
    try {
      const data = await api<RetrievalResult>("search", {
        method: "POST",
        signal: controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          knowledge_base_ids: [base.id],
          query,
          retrieval_config: config,
          diagnostics: true,
        }),
      });
      if (!controller.signal.aborted) setResult(data);
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "检索失败");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!saved || !valid()) return;
    setSaving(true);
    setError("");
    try {
      const data = await api<RetrievalConfig>("retrieval-config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      setSaved(data);
      toast.success("检索设置已保存，将用于本账号后续知识库提问");
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }
  const changed = saved && JSON.stringify(saved) !== JSON.stringify(config);
  return (
    <section className="space-y-6" aria-label="检索测试工作区">
      <div>
        <h3 className="text-lg font-medium">检索测试</h3>
        <p className="text-muted-foreground mt-2 text-sm leading-6">
          输入问题，检查“{base.name}”能找到哪些原文。先测试效果，再决定是否保存检索设置。
        </p>
      </div>
      <div className="space-y-2 sm:hidden">
        <label htmlFor={`${id}-mobile-mode`} className="block text-sm">
          检索方式
        </label>
        <select
          id={`${id}-mobile-mode`}
          disabled={!saved || saving}
          value={config.mode}
          onChange={(e) => edit({ ...config, mode: e.target.value as RetrievalConfig["mode"] })}
          className="bg-background h-11 w-full rounded-lg border px-3 text-sm"
        >
          {modes.map((mode) => (
            <option key={mode.value} value={mode.value}>
              {mode.label}
            </option>
          ))}
        </select>
        <p className="text-muted-foreground text-xs">
          {modes.find((mode) => mode.value === config.mode)?.description}
        </p>
      </div>
      <fieldset disabled={!saved || saving} className="hidden gap-3 sm:grid sm:grid-cols-3">
        <legend className="sr-only">检索模式</legend>
        {modes.map((mode) => (
          <label
            key={mode.value}
            className={`cursor-pointer rounded-xl border p-4 ${config.mode === mode.value ? "border-brand bg-brand/5" : "hover:bg-muted/40"}`}
          >
            <span className="flex items-center gap-2 text-sm font-medium">
              <input
                type="radio"
                name={`${id}-mode`}
                value={mode.value}
                checked={config.mode === mode.value}
                onChange={() => edit({ ...config, mode: mode.value })}
                className="accent-brand"
              />
              {mode.label}
            </span>
            <span className="text-muted-foreground mt-2 block text-xs leading-5">
              {mode.description}
            </span>
          </label>
        ))}
      </fieldset>
      <form onSubmit={run} className="flex flex-col gap-3 sm:flex-row">
        <Input
          aria-label="检索问题"
          placeholder="例如：差旅住宿的报销上限是多少？"
          maxLength={1500}
          value={query}
          onChange={(e) => {
            invalidate();
            setQuery(e.target.value);
          }}
          className="min-w-0 flex-1"
        />
        <Button
          type="submit"
          className="mint-action"
          disabled={!saved || busy || saving || !query.trim() || readyCount === 0}
        >
          {busy ? (config.rerank_enabled ? "检索与重排中…" : "检索中…") : "开始检索"}
        </Button>
      </form>
      {readyCount === 0 && (
        <p className="text-muted-foreground text-sm">
          暂无可检索文件，请先在“文件管理”上传资料并等待处理完成。
        </p>
      )}
      <details className="rounded-xl border p-4" open={!saved || undefined}>
        <summary className="cursor-pointer text-sm">
          高级检索设置{" "}
          <span className="text-muted-foreground ml-2 text-xs">
            {!saved ? "正在读取设置" : changed ? "有未保存的调整" : "使用账号已保存设置"}
          </span>
        </summary>
        <form ref={form} onSubmit={save} className="mt-5 space-y-5">
          <p className="text-muted-foreground text-xs leading-6">
            调整后可直接测试。点击保存后，对本账号所有知识库及后续知识库提问生效；无需重新处理文件。
          </p>
          <fieldset disabled={!saved || saving} className="grid gap-3 sm:grid-cols-2">
            <legend className="sr-only">增强检索</legend>
            <label htmlFor={`${id}-rerank`} className="rounded-xl border p-4 text-sm">
              <span className="flex items-center gap-2">
                <input
                  id={`${id}-rerank`}
                  type="checkbox"
                  aria-label="启用本地重排"
                  checked={config.rerank_enabled}
                  onChange={(e) => edit({ ...config, rerank_enabled: e.target.checked })}
                  className="accent-brand"
                />
                本地模型重排
              </span>
              <span className="text-muted-foreground mt-2 block text-xs leading-6">
                用中文模型重新比较候选内容。耗时随候选数增加，可先测试再保存。
              </span>
            </label>
            <label htmlFor={`${id}-context`} className="rounded-xl border p-4 text-sm">
              <span className="flex items-center gap-2">
                <input
                  id={`${id}-context`}
                  type="checkbox"
                  aria-label="启用回答前上下文扩展"
                  checked={config.context_enabled}
                  onChange={(e) => edit({ ...config, context_enabled: e.target.checked })}
                  className="accent-brand"
                />
                回答前补充上下文
              </span>
              <span className="text-muted-foreground mt-2 block text-xs leading-6">
                从命中文档的当前索引取相邻片段。总计最多 10 段，每段保留自己的原文引用。
              </span>
            </label>
          </fieldset>
          <fieldset
            disabled={!saved || saving}
            className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
          >
            <legend className="sr-only">检索参数</legend>
            {fields.map((field) => {
              const disabled =
                (field.key === "rerank_limit" && !config.rerank_enabled) ||
                (["context_window", "context_char_budget"].includes(field.key) &&
                  !config.context_enabled) ||
                (field.key === "semantic_threshold" && config.mode === "keyword") ||
                (field.key === "keyword_threshold" && config.mode === "semantic") ||
                (["semantic_weight", "keyword_weight", "rrf_k"].includes(field.key) &&
                  config.mode !== "hybrid");
              return (
                <label
                  key={field.key}
                  htmlFor={`${id}-${field.key}`}
                  className={`block space-y-2 text-sm ${disabled ? "opacity-50" : ""}`}
                >
                  <span>{field.label}</span>
                  <Input
                    id={`${id}-${field.key}`}
                    type="number"
                    required
                    min={field.min}
                    max={field.max}
                    step={field.step}
                    disabled={disabled}
                    value={config[field.key]}
                    onChange={(e) => edit({ ...config, [field.key]: Number(e.target.value) })}
                  />
                  <span className="text-muted-foreground block text-xs leading-5">
                    {field.hint}
                  </span>
                </label>
              );
            })}
          </fieldset>
          <div className="flex flex-wrap gap-3">
            <Button type="submit" disabled={!saved || saving || !changed}>
              {saving ? "正在保存…" : "保存为账号检索设置"}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={!saved || saving}
              onClick={() => edit({ ...DEFAULT_RETRIEVAL_CONFIG })}
            >
              恢复推荐参数
            </Button>
            {changed && (
              <Button type="button" variant="ghost" disabled={saving} onClick={() => edit(saved!)}>
                撤销调整
              </Button>
            )}
          </div>
        </form>
      </details>
      {error && (
        <div role="alert" className="text-destructive text-sm">
          {error}
          {!saved && (
            <Button variant="outline" onClick={() => setReload(reload + 1)}>
              重新加载设置
            </Button>
          )}
        </div>
      )}
      {!saved && !error && (
        <p role="status" className="text-muted-foreground text-sm">
          正在加载检索设置…
        </p>
      )}
      {result && (
        <div className="space-y-4" aria-live="polite">
          <div className="bg-muted/20 rounded-xl border p-4">
            <p className="text-muted-foreground mb-2 text-xs">
              {result.diagnostics.engine === "postgres"
                ? "数据库内检索 · 中文分词 BM25 + pgvector"
                : "应用内检索 · 中文双字匹配"}
            </p>
            <p className="text-sm font-medium">
              找到 {result.diagnostics.returned} 个片段 · {result.diagnostics.total_ms} ms
            </p>
            <p className="text-muted-foreground mt-2 text-xs leading-6">
              检索范围 {result.diagnostics.total_chunks} 块 → 合并候选{" "}
              {result.diagnostics.merged_candidates} 块 → 去除重叠{" "}
              {result.diagnostics.overlap_removed} 块 → 数量上限截去{" "}
              {result.diagnostics.limit_removed} 块
              {result.diagnostics.context?.added
                ? ` → 补充上下文 ${result.diagnostics.context.added} 块`
                : ""}
            </p>
            <details className="mt-2 text-xs leading-6">
              <summary className="text-muted-foreground cursor-pointer">查看本次检索诊断</summary>
              {result.diagnostics.engine === "postgres" && (
                <p>
                  已验证索引 {result.diagnostics.indexed_chunks}{" "}
                  块；向量采用账号范围内的精确排序。分词版本：{result.diagnostics.tokenizer}
                  。模型指纹：{result.diagnostics.model_fingerprint?.slice(0, 12)}。
                </p>
              )}
              <p>
                关键词：{result.diagnostics.keyword_eligible} 块达到下限，保留{" "}
                {result.diagnostics.keyword_candidates} 块候选。
              </p>
              <p>
                语义：{result.diagnostics.semantic_eligible} 块达到下限，保留{" "}
                {result.diagnostics.semantic_candidates} 块候选。查询向量耗时{" "}
                {result.diagnostics.embedding_ms} ms。
              </p>
              {result.diagnostics.rerank?.status === "applied" && (
                <p>
                  本地重排：{result.diagnostics.rerank.candidates} 个候选，耗时{" "}
                  {result.diagnostics.rerank.elapsed_ms} ms。模型 {result.diagnostics.rerank.model}
                  。
                  {result.diagnostics.rerank.truncated_pairs
                    ? `其中 ${result.diagnostics.rerank.truncated_pairs} 组输入按模型 ${result.diagnostics.rerank.max_tokens} token 上限截断，引用保留完整片段。`
                    : ""}
                </p>
              )}
              {result.diagnostics.context?.enabled && (
                <p>
                  核心命中 {result.diagnostics.context.seed_count} 段；补充{" "}
                  {result.diagnostics.context.added} 段，共 {result.diagnostics.context.added_chars}{" "}
                  字符；因数量或字数预算跳过 {result.diagnostics.context.budget_skipped}{" "}
                  次候选扩展。
                </p>
              )}
              <p className="text-muted-foreground">
                得分用于当前检索排序，不代表答案正确率。未启用的检索分支不产生候选。
              </p>
            </details>
          </div>
          {!result.items.length && (
            <p className="text-muted-foreground rounded-xl border border-dashed p-6 text-sm">
              未找到满足条件的片段。可更换问法、降低得分下限，或检查资料是否包含相关内容。
            </p>
          )}
          {result.items.map((hit, index) => (
            <article key={hit.id} className="rounded-xl border p-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h4 className="text-brand text-sm break-all">
                  {index + 1}. {hit.title}
                  {hit.page ? ` · 第 ${hit.page} 页` : ""}
                </h4>
                <span className="text-muted-foreground text-xs">
                  {hit.score_type === "context"
                    ? "补充上下文"
                    : `${hit.score_type === "reranker" ? "本地重排" : hit.score_type.toUpperCase()} ${hit.score.toFixed(4)}`}
                </span>
              </div>
              <p className="mt-3 text-sm leading-7 break-words whitespace-pre-wrap">
                {hit.content}
              </p>
              <div className="text-muted-foreground mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs">
                {hit.score_type === "context" ? (
                  <span>相邻原文 · 独立引用</span>
                ) : (
                  <>
                    {hit.retrieval.rerank_rank && (
                      <span>
                        重排第 {hit.retrieval.rerank_rank} 名 · 原候选第{" "}
                        {hit.retrieval.initial_rank} 名
                      </span>
                    )}
                    <span>
                      关键词
                      {hit.retrieval.keyword_rank
                        ? `第 ${hit.retrieval.keyword_rank} 名`
                        : "未入选"}
                      {hit.retrieval.keyword_score !== null
                        ? ` · ${hit.retrieval.keyword_score.toFixed(3)}`
                        : ""}
                    </span>
                    <span>
                      语义
                      {hit.retrieval.semantic_rank
                        ? `第 ${hit.retrieval.semantic_rank} 名`
                        : "未入选"}
                      {hit.retrieval.semantic_score !== null
                        ? ` · ${hit.retrieval.semantic_score.toFixed(3)}`
                        : ""}
                    </span>
                  </>
                )}
                <a href={hit.url} className="underline underline-offset-4">
                  下载原文
                </a>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
