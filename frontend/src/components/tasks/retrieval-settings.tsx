"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/stores";
import { knowledgeRequest, type RetrievalConfig } from "@/lib/knowledge";
import { Button } from "@/components/ui";

export type RetrievalSnapshot = {
  configuration_id: string;
  origin: "account" | "task_override";
  config: RetrievalConfig;
  result_limit_capped: boolean;
};
export type RetrievalRecord = {
  query: string;
  configuration_id: string;
  config: RetrievalConfig;
  engine?: string;
  tokenizer?: string;
  model_fingerprint?: string;
  returned?: number;
  total_ms?: number;
  keyword_candidates?: number;
  semantic_candidates?: number;
  rerank?: {
    status: string;
    candidates: number;
    elapsed_ms: number;
    model?: string;
    revision?: string;
  };
  context?: { enabled: boolean; added?: number; added_chars?: number };
};

function ConfigSummary({ config, zh }: { config: RetrievalConfig; zh: boolean }) {
  const t = (cn: string, en: string) => (zh ? cn : en);
  const modes = {
    hybrid: t("混合检索", "Hybrid"),
    keyword: t("关键词检索", "Keyword"),
    semantic: t("语义检索", "Semantic"),
  };
  return (
    <div className="space-y-2 text-xs leading-6">
      <p>
        {modes[config.mode]} · {t("核心片段", "Core passages")} {config.result_limit} ·{" "}
        {t("每路候选", "Candidates per branch")} {config.candidate_limit}
      </p>
      <p>
        {t("本地重排", "Local rerank")} {config.rerank_enabled ? t("开启", "On") : t("关闭", "Off")}{" "}
        · {t("上下文扩展", "Context expansion")}{" "}
        {config.context_enabled ? t("开启", "On") : t("关闭", "Off")}
      </p>
      <details>
        <summary className="cursor-pointer py-1">
          {t("全部检索参数", "All retrieval parameters")}
        </summary>
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
          {[
            [t("语义下限", "Semantic threshold"), config.semantic_threshold],
            [t("关键词下限", "Keyword threshold"), config.keyword_threshold],
            [t("语义权重", "Semantic weight"), config.semantic_weight],
            [t("关键词权重", "Keyword weight"), config.keyword_weight],
            [t("排名平滑值", "RRF smoothing"), config.rrf_k],
            [t("重排候选数", "Rerank candidates"), config.rerank_limit],
            [t("上下文范围", "Context window"), config.context_window],
            [t("上下文字数预算", "Context character budget"), config.context_char_budget],
          ].map(([label, value]) => (
            <div key={label} className="min-w-0">
              <dt className="text-muted-foreground break-words">{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        <p className="text-muted-foreground mt-2">
          {t(
            "关闭的检索分支和增强选项不执行，其参数仅作为保留设置。",
            "Disabled branches and enhancements are not executed; their settings remain stored.",
          )}
        </p>
      </details>
    </div>
  );
}

export function TaskRetrievalSettings({
  value,
  onChange,
  collaboration,
  zh,
}: {
  value: RetrievalConfig | null;
  onChange: (value: RetrievalConfig | null) => void;
  collaboration: boolean;
  zh: boolean;
}) {
  const userId = useAuthStore((s) => s.user?.id);
  const t = (cn: string, en: string) => (zh ? cn : en);
  const query = useQuery({
    queryKey: ["task-retrieval-defaults", userId],
    queryFn: ({ signal }) => knowledgeRequest<RetrievalConfig>("retrieval-config", { signal }),
    enabled: !!userId,
    staleTime: 0,
  });
  const config = value || query.data;
  return (
    <fieldset className="border-border space-y-3 rounded-xl border p-4">
      <legend className="px-1 text-sm font-medium">
        {t("本次任务的检索设置", "Retrieval settings for this task")}
      </legend>
      <label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={!!value}
          disabled={!value && !query.data}
          onChange={(e) => onChange(e.target.checked ? { ...query.data! } : null)}
          className="accent-emerald-500"
        />
        {t("自定义本次检索", "Customize this task")}
      </label>
      <p className="text-muted-foreground text-xs leading-6">
        {value
          ? t(
              "仅用于本次任务，不修改账号默认设置。",
              "Applies only to this task; account defaults are unchanged.",
            )
          : t(
              "预览账号默认设置；以服务端接收任务时的设置为准，提交后固定。",
              "Preview of account defaults. The server captures and fixes them when accepting the task.",
            )}
      </p>
      {value && (
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-2 text-sm">
            <span>{t("任务检索方式", "Task retrieval mode")}</span>
            <select
              aria-label={t("任务检索方式", "Task retrieval mode")}
              value={value.mode}
              onChange={(e) =>
                onChange({ ...value, mode: e.target.value as RetrievalConfig["mode"] })
              }
              className="border-input bg-background h-11 w-full rounded-lg border px-3"
            >
              <option value="hybrid">{t("混合检索", "Hybrid")}</option>
              <option value="keyword">{t("关键词检索", "Keyword")}</option>
              <option value="semantic">{t("语义检索", "Semantic")}</option>
            </select>
          </label>
          <label className="space-y-2 text-sm">
            <span>{t("任务核心片段数", "Core passages for this task")}</span>
            <select
              aria-label={t("任务核心片段数", "Core passages for this task")}
              value={value.result_limit}
              onChange={(e) => onChange({ ...value, result_limit: Number(e.target.value) })}
              className="border-input bg-background h-11 w-full rounded-lg border px-3"
            >
              {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={value.rerank_enabled}
              onChange={(e) => onChange({ ...value, rerank_enabled: e.target.checked })}
              className="accent-emerald-500"
            />
            {t("本次启用本地重排", "Rerank for this task")}
          </label>
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={value.context_enabled}
              onChange={(e) => onChange({ ...value, context_enabled: e.target.checked })}
              className="accent-emerald-500"
            />
            {t("本次补充上下文", "Expand context for this task")}
          </label>
        </div>
      )}
      {config && <ConfigSummary config={config} zh={zh} />}
      {collaboration && (
        <p className="text-muted-foreground text-xs leading-6">
          {t(
            "资料协作每次检索最多选取 5 个核心片段，最终合并最多 10 个片段；超过上限的设置会在提交时收紧。",
            "Collaboration selects up to 5 core passages per query and merges up to 10 passages. Higher limits are capped on submission.",
          )}
        </p>
      )}
      {query.isPending && (
        <p role="status" className="text-muted-foreground text-xs">
          {t("正在读取账号设置…", "Loading account defaults…")}
        </p>
      )}
      {query.isError && (
        <p className="text-muted-foreground text-xs">
          {t(
            "无法预览账号设置；仍可由服务器在提交时读取。",
            "Preview unavailable; the server can still read defaults on submission.",
          )}{" "}
          <Button type="button" variant="ghost" size="sm" onClick={() => query.refetch()}>
            {t("重新加载", "Reload")}
          </Button>
        </p>
      )}
    </fieldset>
  );
}

export function RetrievalSnapshotPanel({
  snapshot,
  records,
  zh,
}: {
  snapshot?: RetrievalSnapshot;
  records: RetrievalRecord[];
  zh: boolean;
}) {
  const t = (cn: string, en: string) => (zh ? cn : en);
  return (
    <section
      className="border-border bg-card rounded-2xl border p-5 sm:p-7"
      aria-label={t("检索配置与记录", "Retrieval settings and records")}
    >
      <details>
        <summary className="cursor-pointer text-sm font-semibold">
          {t("检索配置与记录", "Retrieval settings and records")}{" "}
          <span className="text-muted-foreground ml-2 text-xs font-normal">
            {records.length
              ? t(`${records.length} 次检索`, `${records.length} retrievals`)
              : t("查看本次设置", "View settings")}
          </span>
        </summary>
        {snapshot ? (
          <div className="mt-4 space-y-3">
            <p className="text-muted-foreground text-xs leading-6">
              {snapshot.origin === "account"
                ? t("提交时的账号设置", "Account defaults at submission")
                : t("本次自定义设置", "Task-specific settings")}{" "}
              · {t("已固定", "Fixed")}
            </p>
            <ConfigSummary config={snapshot.config} zh={zh} />
            <p className="text-muted-foreground text-xs">
              {t("参数指纹", "Parameter fingerprint")}：{snapshot.configuration_id.slice(0, 12)}
            </p>
            {snapshot.result_limit_capped && (
              <p className="text-muted-foreground text-xs">
                {t(
                  "已按资料协作预算收紧至每次 5 个核心片段。",
                  "Capped at 5 core passages per query for collaboration.",
                )}
              </p>
            )}
          </div>
        ) : (
          <p className="text-muted-foreground mt-3 text-xs">
            {t(
              "旧任务未保存提交时的参数快照；下方如有记录，代表实际检索时使用的设置。",
              "This older task has no submission snapshot. Records below show settings actually used during retrieval.",
            )}
          </p>
        )}
        <p className="text-muted-foreground mt-3 text-xs leading-6">
          {t(
            "固定参数不冻结资料内容，也不保证模型生成完全相同的答案。每次执行仍检查资料权限；下方记录实际检索引擎与模型身份。",
            "Fixed parameters do not freeze source contents or guarantee identical generated answers. Access is rechecked; records identify the actual retrieval engine and model.",
          )}
        </p>
        {records.length === 0 ? (
          <p className="text-muted-foreground mt-4 text-sm">
            {t("暂无已完成的检索记录", "No completed retrieval records yet")}
          </p>
        ) : (
          <div className="mt-4 space-y-3">
            {records.map((record, i) => (
              <details key={i} className="border-border rounded-xl border p-3 text-sm">
                <summary className="cursor-pointer leading-6 break-words">
                  {i + 1}. {record.query}{" "}
                  <span className="text-muted-foreground text-xs">
                    · {record.returned ?? "—"} {t("段", "passages")} · {record.total_ms ?? "—"} ms
                  </span>
                </summary>
                <div className="mt-3 space-y-2 text-xs leading-6">
                  <p>
                    {record.engine === "postgres"
                      ? t("数据库内检索", "Database retrieval")
                      : record.engine === "legacy"
                        ? t("应用内检索", "Application retrieval")
                        : t("引擎未记录", "Engine not recorded")}{" "}
                    · {t("关键词候选", "Keyword candidates")} {record.keyword_candidates ?? "—"} ·{" "}
                    {t("语义候选", "Semantic candidates")} {record.semantic_candidates ?? "—"}
                  </p>
                  <ConfigSummary config={record.config} zh={zh} />
                  {record.rerank && (
                    <p>
                      {t("重排状态", "Rerank status")}：
                      {record.rerank.status === "applied"
                        ? t("已执行", "Applied")
                        : record.rerank.status === "disabled"
                          ? t("未启用", "Disabled")
                          : record.rerank.status === "no_candidates"
                            ? t("无候选", "No candidates")
                            : t("状态未识别", "Unknown status")}
                    </p>
                  )}
                  {record.rerank?.model && (
                    <p className="break-all">
                      {t("实际重排模型", "Actual rerank model")}：{record.rerank.model}{" "}
                      {record.rerank.revision?.slice(0, 12)}
                    </p>
                  )}
                  {record.context && (
                    <p>
                      {t("上下文扩展", "Context expansion")}：
                      {record.context.enabled
                        ? t(
                            `已补充 ${record.context.added ?? 0} 段，共 ${record.context.added_chars ?? 0} 字`,
                            `${record.context.added ?? 0} passages, ${record.context.added_chars ?? 0} characters added`,
                          )
                        : t("未启用", "Disabled")}
                    </p>
                  )}
                  {record.tokenizer && (
                    <p className="break-all">
                      {t("分词版本", "Tokenizer")}：{record.tokenizer}
                    </p>
                  )}
                  {record.model_fingerprint && (
                    <p>
                      {t("向量模型指纹", "Embedding fingerprint")}：
                      {record.model_fingerprint.slice(0, 12)}
                    </p>
                  )}
                </div>
              </details>
            ))}
          </div>
        )}
      </details>
    </section>
  );
}
