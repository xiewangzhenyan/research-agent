"use client";
import { useUnsavedInput } from "@/hooks/use-unsaved-input";
import { currentProject, projectFetch } from "@/lib/project-scope";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useLocale } from "next-intl";
import { CheckCircle2, Clock3, ListTodo, Plus, Send, Square, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui";
import { PageHeader } from "@/components/dashboard/page-header";
import { MarkdownContent } from "@/components/chat/markdown-content";
import { useAuthStore } from "@/stores";
import { CollaborationProgress, type RoleEvent } from "@/components/tasks/collaboration-progress";
import {
  TaskRetrievalSettings,
  RetrievalSnapshotPanel,
  type RetrievalSnapshot,
  type RetrievalRecord,
} from "@/components/tasks/retrieval-settings";
import type { RetrievalConfig } from "@/lib/knowledge";
import { CodeExecutionPanel, type ExecutionResult } from "@/components/tasks/code-execution-panel";
import { InputFiles, type InputFile } from "@/components/tasks/input-files";
import { ArtifactPanel } from "@/components/tasks/artifact-panel";
import { fetchTools } from "@/lib/tool-catalog";
import { useGenerationConfig } from "@/hooks/use-generation-config";

type Task = {
  id: string;
  request: {
    prompt: string;
    knowledge_base_ids: string[];
    tools?: string[];
    tool_policy_version?: string;
    retrieval_snapshot?: RetrievalSnapshot;
    mode?: "standard" | "knowledge_collaboration";
  };
  status: string;
  effective_config: {
    model: string;
    thinking_effort?: string;
    temperature?: number;
    policy_version: string;
  };
  attempt: number;
  event_seq: number;
  error: string | null;
  created_at: string;
  result: {
    content: string;
    retrieval_runs?: RetrievalRecord[];
    citations: {
      index: number;
      title?: string;
      document_name?: string;
      filename?: string;
      content: string;
      quotes?: string[];
      page?: number;
      page_number?: number;
    }[];
  } | null;
  pending_input: {
    question_id: string;
    calls: { call_id: string; questions: { question: string; options: string[] }[] }[];
  } | null;
};
type TaskEvent = {
  seq: number;
  kind: string;
  data: RoleEvent["data"] &
    ExecutionResult & {
      message?: string;
      tool?: string;
      attempt?: number;
      code?: string;
      stdout?: string;
      stderr?: string;
      exit_code?: number;
      state?: string;
      truncated?: boolean;
      execution_id?: string;
      retrieval?: RetrievalRecord;
    };
  created_at: string;
};
const terminal = (status: string) => ["completed", "cancelled", "failed"].includes(status);
const labels: Record<string, [string, string]> = {
  queued: ["排队中", "Queued"],
  running: ["执行中", "Running"],
  waiting_input: ["待补充信息", "Needs input"],
  cancelling: ["正在取消", "Cancelling"],
  cancelled: ["已取消", "Cancelled"],
  completed: ["已完成", "Completed"],
  failed: ["执行失败", "Failed"],
};
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await projectFetch(path, { cache: "no-store", ...init });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : data.error?.message || data.message || "请求失败，请稍后重试",
    );
  return data;
}

export default function TasksPage() {
  const userId = useAuthStore((s) => s.user?.id);
  return <TasksWorkspace key={`${userId}:${currentProject()?.id ?? "default"}`} />;
}

function TasksWorkspace() {
  const zh = useLocale() === "zh";
  const t = (cn: string, en: string) => (zh ? cn : en);
  const user = useAuthStore((s) => s.user);
  const search = useSearchParams();
  const [selected, setSelected] = useState<string | null>(search.get("id"));
  const [task, setTask] = useState<Task | null>(null);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [inputFiles, setInputFiles] = useState<InputFile[]>([]);
  const [uploadingFiles, setUploadingFiles] = useState(false);
  const [prompt, setPrompt] = useState("");
  useUnsavedInput(!!prompt.trim() || uploadingFiles || inputFiles.length > 0);
  const [mode, setMode] = useState<"standard" | "knowledge_collaboration">("standard");
  const [model, setModel] = useState("");
  const [tools, setTools] = useState<string[]>(["current_datetime", "ask_user"]);
  const toolQuery = useQuery({
    queryKey: ["tools", user?.id],
    queryFn: ({ signal }) => fetchTools(signal),
    enabled: !!user,
    staleTime: 15000,
  });
  const [retrieval, setRetrieval] = useState<RetrievalConfig | null>(null);
  const [bases, setBases] = useState<string[]>(() => [
    ...(currentProject()?.knowledge_base_ids ?? []),
  ]);
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [error, setError] = useState("");
  const [pollError, setPollError] = useState("");
  const [busy, setBusy] = useState(false);
  const [offset, setOffset] = useState(0);
  const submission = useRef({ hash: "", key: "" });
  const capabilities = useGenerationConfig();
  const knowledge = useQuery({
    queryKey: ["task-knowledge-bases", user?.id],
    queryFn: () => api<{ items: { id: string; name: string }[] }>("/api/knowledge/bases"),
    enabled: !!user,
  });
  const list = useQuery({
    queryKey: ["tasks", user?.id, currentProject()?.id, offset],
    queryFn: () => api<Task[]>(`/api/tasks?offset=${offset}`),
    enabled: !!user,
    refetchInterval: 5000,
  });

  function select(id: string | null) {
    setSelected(id);
    setTask(null);
    setEvents([]);
    setAnswers({});
    setError("");
    setPollError("");
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("id", id);
    else url.searchParams.delete("id");
    window.history.replaceState(null, "", url);
  }
  useEffect(() => {
    if (!selected || !user) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let cursor = 0;
    let collected: TaskEvent[] = [];
    async function poll() {
      try {
        const current = await api<Task>(`/api/tasks/${selected}`, { signal: controller.signal });
        let page: TaskEvent[];
        do {
          page = await api<TaskEvent[]>(`/api/tasks/${selected}/events?after=${cursor}`, {
            signal: controller.signal,
          });
          collected = [...collected, ...page].slice(-1000);
          cursor = page.at(-1)?.seq ?? cursor;
        } while (page.length === 100);
        if (controller.signal.aborted) return;
        setTask(current);
        setEvents(collected);
        setPollError("");
        if (terminal(current.status)) return;
      } catch (e) {
        if (controller.signal.aborted) return;
        setPollError(e instanceof Error ? e.message : "连接中断，正在重连");
      }
      timer = setTimeout(poll, 2000);
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [selected, user]);

  async function submit() {
    if (uploadingFiles) return;
    setBusy(true);
    setError("");
    try {
      const payload = {
        prompt,
        input_file_ids:
          mode === "standard" && tools.includes("run_python") && !bases.length
            ? inputFiles.map((f) => f.id)
            : [],
        knowledge_base_ids: bases,
        ...(bases.length && retrieval ? { retrieval_config: retrieval } : {}),
        tools: mode === "knowledge_collaboration" ? [] : tools,
        mode,
        generation: { model: model || capabilities.data?.default },
      };
      const hash = JSON.stringify(payload);
      if (submission.current.hash !== hash) submission.current = { hash, key: crypto.randomUUID() };
      const created = await api<Task>("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...payload, idempotency_key: submission.current.key }),
      });
      submission.current = { hash: "", key: "" };
      select(created.id);
      setTask(created);
      setPrompt("");
      setInputFiles([]);
      setOffset(0);
      void list.refetch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交失败");
    } finally {
      setBusy(false);
    }
  }
  async function action(kind: "cancel" | "resume") {
    if (!task) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api<Task>(`/api/tasks/${task.id}/${kind}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body:
          kind === "resume"
            ? JSON.stringify({ question_id: task.pending_input?.question_id, answers })
            : undefined,
      });
      setTask(updated);
      setAnswers({});
      void list.refetch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }
  const pending = task?.status === "waiting_input" ? task.pending_input : null;
  const canResume =
    !!pending &&
    pending.calls.every((c) => c.questions.every((_, i) => answers[c.call_id]?.[i]?.trim()));
  const status = (value: string) => labels[value]?.[zh ? 0 : 1] || value;
  return (
    <div className="tasks-workspace space-y-6 pb-8">
      <PageHeader
        eyebrow={t("持续执行", "BACKGROUND WORK")}
        title={t("后台任务", "Tasks")}
        description={t(
          "提交任务后可离开页面，回来查看执行记录、补充信息与最终结果。",
          "Start work, leave the page and return to its progress, questions and results.",
        )}
      />
      <div className="task-workspace-grid grid items-start gap-6 xl:grid-cols-[248px_minmax(0,1fr)]">
        <aside className="task-history-panel p-3">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-semibold">{t("我的任务", "My tasks")}</h2>
            <Button size="sm" onClick={() => select(null)}>
              <Plus size={15} className="mr-1" />
              {t("新建", "New")}
            </Button>
          </div>
          {list.isPending && (
            <p role="status" className="text-muted-foreground py-6 text-sm">
              {t("正在加载…", "Loading…")}
            </p>
          )}
          {list.isError && (
            <Button variant="outline" onClick={() => list.refetch()}>
              {t("加载失败，点击重试", "Retry loading")}
            </Button>
          )}
          {list.data?.length === 0 && (
            <p className="text-muted-foreground py-8 text-center text-sm">
              {t("还没有任务，从右侧开始", "No tasks yet. Create your first task.")}
            </p>
          )}
          <div className="max-h-[320px] space-y-2 overflow-y-auto xl:max-h-[65vh]">
            {list.data
              ?.map((item) => (item.id === task?.id ? task : item))
              .map((item) => (
                <button
                  type="button"
                  key={item.id}
                  onClick={() => select(item.id)}
                  aria-current={selected === item.id ? "true" : undefined}
                  className={`w-full rounded-xl border p-3 text-left transition-colors ${selected === item.id ? "border-brand/50 bg-brand/10" : "hover:bg-accent border-transparent"}`}
                >
                  <p className="line-clamp-2 text-sm leading-6 break-words">
                    {item.request.prompt}
                  </p>
                  <div className="text-muted-foreground mt-2 flex justify-between gap-2 text-xs">
                    <span
                      className={
                        item.status === "waiting_input"
                          ? "text-amber-500"
                          : item.status === "completed"
                            ? "text-brand"
                            : ""
                      }
                    >
                      {status(item.status)}
                    </span>
                    <time>
                      {new Date(item.created_at).toLocaleDateString(zh ? "zh-CN" : "en-US")}
                    </time>
                  </div>
                </button>
              ))}
          </div>
          <div className="mt-3 flex justify-between">
            <Button
              size="sm"
              variant="ghost"
              disabled={!offset}
              onClick={() => setOffset((v) => Math.max(0, v - 50))}
            >
              {t("上一页", "Previous")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={(list.data?.length ?? 0) < 50}
              onClick={() => setOffset((v) => v + 50)}
            >
              {t("下一页", "Next")}
            </Button>
          </div>
        </aside>
        <section aria-label={t("任务详情", "Task details")} className="min-w-0 space-y-5">
          {(error || pollError) && (
            <p
              role="alert"
              className="border-destructive/30 bg-destructive/5 rounded-xl border p-4 text-sm"
            >
              {error || pollError}
            </p>
          )}
          {!selected ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void submit();
              }}
              className="task-compose-panel bg-card space-y-5 rounded-xl border p-5 sm:p-7"
            >
              <div className="flex items-center gap-3">
                <span className="text-brand bg-brand/10 rounded-xl p-3">
                  <ListTodo size={22} />
                </span>
                <div>
                  <h2 className="text-lg font-semibold">{t("创建后台任务", "Create a task")}</h2>
                  <p className="text-muted-foreground mt-1 text-sm">
                    {t(
                      "清晰描述目标、要求与期望的输出格式。",
                      "Describe the objective, constraints and expected format.",
                    )}
                  </p>
                </div>
              </div>
              <fieldset className="space-y-3">
                <legend className="text-sm font-medium">{t("执行方式", "Execution mode")}</legend>
                <div className="grid gap-3 sm:grid-cols-2">
                  {(["standard", "knowledge_collaboration"] as const).map((value) => (
                    <label
                      key={value}
                      className={`cursor-pointer rounded-xl border p-4 ${mode === value ? "border-brand/50 bg-brand/10" : "border-border"}`}
                    >
                      <span className="flex items-center gap-2 text-sm font-medium">
                        <input
                          type="radio"
                          name="task-mode"
                          value={value}
                          checked={mode === value}
                          onChange={() => setMode(value)}
                          className="accent-emerald-500"
                        />
                        {value === "standard"
                          ? t("标准任务", "Standard task")
                          : t("资料协作", "Knowledge collaboration")}
                      </span>
                      <span className="text-muted-foreground mt-2 block text-xs leading-6">
                        {value === "standard"
                          ? t(
                              "直接完成问答或调用已授权工具。",
                              "Answer questions or use authorized tools.",
                            )
                          : t(
                              "规划、研究、撰写、审校，适合多角度整理资料。",
                              "Plan, research, write and review from your sources.",
                            )}
                      </span>
                    </label>
                  ))}
                </div>
                {mode === "knowledge_collaboration" && (
                  <p className="text-muted-foreground text-xs leading-6">
                    {t(
                      "请选择知识库。四个角色共享本次模型配置，仅访问所选资料，最多修订一次；通常比标准问答耗时更长。",
                      "Choose a knowledge base. Four roles share the model configuration, use only selected sources and revise at most once. This usually takes longer than standard Q&A.",
                    )}
                  </p>
                )}
              </fieldset>
              <label className="block space-y-2 text-sm">
                <span>{t("任务内容", "Task instructions")}</span>
                <textarea
                  aria-label={t("任务内容", "Task instructions")}
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  maxLength={1500}
                  required
                  rows={6}
                  placeholder={t(
                    "例如：根据选定知识库整理入门指南，说明关键概念，并标出每个结论的原文依据。",
                    "For example: create an introduction from the selected knowledge bases and cite the supporting passages.",
                  )}
                  className="border-input bg-background focus-visible:ring-brand w-full resize-y rounded-xl border p-4 leading-7 outline-none focus-visible:ring-2"
                />
                <span className="text-muted-foreground block text-right text-xs">
                  {prompt.length} / 1500
                </span>
              </label>
              <label className="block space-y-2 text-sm">
                <span>{t("生成模型", "Generation model")}</span>
                <select
                  value={model || capabilities.data?.default || ""}
                  onChange={(e) => setModel(e.target.value)}
                  className="border-input bg-background h-11 w-full rounded-lg border px-3"
                >
                  {!capabilities.data && (
                    <option value="" disabled>
                      {capabilities.isError
                        ? t("模型配置加载失败", "Models unavailable")
                        : t("正在读取模型…", "Loading models…")}
                    </option>
                  )}
                  {capabilities.data?.models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.id}
                    </option>
                  ))}
                </select>
              </label>
              {capabilities.isError && (
                <Button type="button" variant="outline" onClick={() => capabilities.refetch()}>
                  {t("重新加载模型配置", "Retry loading models")}
                </Button>
              )}
              {mode === "standard" && (
                <fieldset className="space-y-3">
                  <legend className="text-sm">
                    {t("本次任务允许使用的工具", "Allowed tools for this task")}
                  </legend>
                  <div className="flex flex-wrap gap-2">
                    {toolQuery.data?.items.map((item) => (
                      <label
                        key={item.id}
                        className={`border-border flex items-center gap-2 rounded-lg border px-3 py-2 text-sm ${!item.available ? "text-muted-foreground" : "cursor-pointer"}`}
                      >
                        <input
                          type="checkbox"
                          checked={tools.includes(item.id)}
                          disabled={
                            !item.available || (item.id === "run_python" && bases.length > 0)
                          }
                          onChange={(e) =>
                            setTools((v) =>
                              e.target.checked ? [...v, item.id] : v.filter((id) => id !== item.id),
                            )
                          }
                          className="accent-emerald-500"
                        />
                        {zh
                          ? item.label
                          : (
                              {
                                current_datetime: "Current time",
                                ask_user: "Ask user",
                                run_python: "Python",
                              } as Record<string, string>
                            )[item.id]}
                        {!item.available && (
                          <span className="text-xs">{t("未开放", "Unavailable")}</span>
                        )}
                      </label>
                    ))}
                  </div>
                  <p className="text-muted-foreground text-xs leading-6">
                    {t(
                      "取消勾选后，模型无法调用该工具。Python 需要独立沙箱就绪并明确授权。",
                      "Unchecked tools cannot be called. Python needs an isolated runtime and explicit permission.",
                    )}
                  </p>
                  {toolQuery.isError && (
                    <Button type="button" variant="outline" onClick={() => toolQuery.refetch()}>
                      {t("重新加载工具", "Reload tools")}
                    </Button>
                  )}
                </fieldset>
              )}
              {mode === "standard" && (
                <InputFiles
                  files={inputFiles}
                  onChange={setInputFiles}
                  onBusy={setUploadingFiles}
                  enabled={
                    !busy &&
                    !bases.length &&
                    tools.includes("run_python") &&
                    !!toolQuery.data?.sandbox.file_execution &&
                    !!toolQuery.data?.items.find((i) => i.id === "run_python")?.available
                  }
                  zh={zh}
                />
              )}
              <fieldset className="space-y-3">
                <legend className="text-sm">
                  {mode === "knowledge_collaboration"
                    ? t("知识库（必选，最多 5 个）", "Knowledge bases (required, up to 5)")
                    : t("知识库（可选，最多 5 个）", "Knowledge bases (optional, up to 5)")}
                </legend>
                <div className="flex max-h-44 flex-wrap gap-2 overflow-y-auto">
                  {knowledge.isPending && (
                    <p role="status" className="text-muted-foreground text-sm">
                      {t("正在读取知识库…", "Loading knowledge bases…")}
                    </p>
                  )}
                  {knowledge.data?.items.map((base) => (
                    <label
                      key={base.id}
                      className="border-border flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm"
                    >
                      <input
                        type="checkbox"
                        checked={bases.includes(base.id)}
                        disabled={!bases.includes(base.id) && bases.length >= 5}
                        onChange={(e) => {
                          if (e.target.checked)
                            setTools((v) => v.filter((name) => name !== "run_python"));
                          setBases((v) =>
                            e.target.checked ? [...v, base.id] : v.filter((id) => id !== base.id),
                          );
                        }}
                        className="accent-emerald-500"
                      />
                      {base.name}
                    </label>
                  ))}
                </div>
                {knowledge.isError && (
                  <p className="text-destructive text-sm">
                    {t(
                      "知识库加载失败，请刷新页面后重试。",
                      "Knowledge bases unavailable. Refresh to retry.",
                    )}
                  </p>
                )}
                <p className="text-muted-foreground text-xs leading-6">
                  {bases.length
                    ? t(
                        "使用严格资料问答，答案附原文引用；资料不足时会明确说明。",
                        "Strict evidence mode with original quotations; insufficient evidence is stated.",
                      )
                    : t(
                        "未选知识库时，使用通用助手，可查询时间、提出澄清问题。",
                        "Without knowledge bases, the assistant can check time and ask clarifying questions.",
                      )}
                </p>
              </fieldset>
              {bases.length > 0 && (
                <TaskRetrievalSettings
                  value={retrieval}
                  onChange={setRetrieval}
                  collaboration={mode === "knowledge_collaboration"}
                  zh={zh}
                />
              )}
              <div className="border-border flex flex-wrap items-center justify-between gap-3 border-t pt-5">
                <span className="text-muted-foreground text-xs">
                  {t(
                    "每次执行最多 5 分钟，等待补充信息不占用执行时间。",
                    "Up to 5 minutes per execution; waiting for input releases the worker.",
                  )}
                </span>
                <Button
                  type="submit"
                  disabled={
                    busy ||
                    !prompt.trim() ||
                    !capabilities.data ||
                    (mode === "knowledge_collaboration" && bases.length === 0)
                  }
                >
                  <Send size={15} className="mr-2" />
                  {busy ? t("正在提交…", "Submitting…") : t("开始任务", "Start task")}
                </Button>
              </div>
            </form>
          ) : !task ? (
            <div
              role="status"
              className="border-border bg-card rounded-2xl border p-10 text-center"
            >
              {t("正在恢复任务记录…", "Loading task history…")}
            </div>
          ) : (
            <>
              <section className="border-border bg-card rounded-2xl border p-5 sm:p-7">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <span className="text-brand bg-brand/10 inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm">
                    {task.status === "completed" ? (
                      <CheckCircle2 size={16} />
                    ) : (
                      <Clock3 size={16} />
                    )}
                    {status(task.status)}
                  </span>
                  {!terminal(task.status) ? (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy || uploadingFiles || task.status === "cancelling"}
                      onClick={() => action("cancel")}
                    >
                      <Square size={13} className="mr-2" />
                      {t("取消任务", "Cancel task")}
                    </Button>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setMode(task.request.mode || "standard");
                        setRetrieval(task.request.retrieval_snapshot?.config || null);
                        setPrompt(task.request.prompt);
                        setModel(task.effective_config.model);
                        setBases(task.request.knowledge_base_ids);
                        setTools(task.request.tools || ["current_datetime", "ask_user"]);
                        select(null);
                      }}
                    >
                      <RotateCcw size={14} className="mr-2" />
                      {t("用此内容新建", "Create another")}
                    </Button>
                  )}
                </div>
                <h2 className="mt-5 text-lg leading-8 break-words whitespace-pre-wrap">
                  {task.request.prompt}
                </h2>
                <details className="text-muted-foreground mt-4 text-xs">
                  <summary className="cursor-pointer py-2">
                    {t("本次任务配置", "Task configuration")} · {task.effective_config.model}
                  </summary>
                  <p className="mt-2 leading-6 break-all">
                    {t("推理强度", "Reasoning")}:{" "}
                    {(
                      {
                        low: t("低", "Low"),
                        medium: t("中", "Medium"),
                        high: t("高", "High"),
                      } as Record<string, string>
                    )[task.effective_config.thinking_effort || ""] ||
                      t("模型默认", "Model default")}{" "}
                    · {t("温度", "Temperature")}:{" "}
                    {task.effective_config.temperature ?? t("模型默认", "Model default")}
                    <br />
                    {t("配置版本", "Policy")}: {task.effective_config.policy_version}
                    <br />
                    {t("执行次数", "Attempts")}: {task.attempt}
                    <br />
                    {t("已授权工具", "Allowed tools")}:{" "}
                    {(task.request.tools || ["current_datetime", "ask_user"]).join(", ") ||
                      t("无", "None")}
                  </p>
                </details>
                {task.error && (
                  <p role="alert" className="text-destructive mt-4 text-sm">
                    {task.error}
                  </p>
                )}
              </section>
              {task.request.knowledge_base_ids.length > 0 && (
                <RetrievalSnapshotPanel
                  snapshot={task.request.retrieval_snapshot}
                  records={
                    task.result?.retrieval_runs ??
                    events.flatMap((e) =>
                      e.kind === "retrieval_completed" && e.data.retrieval
                        ? [e.data.retrieval]
                        : [],
                    )
                  }
                  zh={zh}
                />
              )}
              {task.request.mode === "knowledge_collaboration" && (
                <CollaborationProgress events={events} status={task.status} zh={zh} />
              )}
              {pending && (
                <form
                  key={pending.question_id}
                  onSubmit={(e) => {
                    e.preventDefault();
                    void action("resume");
                  }}
                  className="border-brand/40 bg-card space-y-4 rounded-2xl border p-5 sm:p-7"
                >
                  <h3 className="font-semibold">
                    {t("补充信息后继续", "Provide details to continue")}
                  </h3>
                  {pending.calls.map((call) => (
                    <div key={call.call_id} className="space-y-5">
                      {call.questions.map((q, index) => (
                        <label key={index} className="block space-y-2 text-sm">
                          <span className="leading-6">{q.question}</span>
                          {q.options.length > 0 && (
                            <span className="text-muted-foreground block text-xs">
                              {t("建议选项：", "Suggestions: ")}
                              {q.options.join(" / ")}
                            </span>
                          )}
                          <textarea
                            required
                            maxLength={2000}
                            value={answers[call.call_id]?.[index] || ""}
                            onChange={(e) =>
                              setAnswers((current) => {
                                const values = [
                                  ...(current[call.call_id] || call.questions.map(() => "")),
                                ];
                                values[index] = e.target.value;
                                return { ...current, [call.call_id]: values };
                              })
                            }
                            className="border-input bg-background w-full rounded-lg border p-3"
                            rows={2}
                          />
                        </label>
                      ))}
                    </div>
                  ))}
                  <Button type="submit" disabled={busy || uploadingFiles || !canResume}>
                    {t("保存并继续执行", "Save and continue")}
                  </Button>
                </form>
              )}
              {task.result && (
                <section className="border-border bg-card rounded-2xl border p-5 sm:p-7">
                  <h3 className="mb-5 font-semibold">{t("任务结果", "Result")}</h3>
                  <div className="min-w-0 overflow-x-auto leading-8 break-words">
                    <MarkdownContent
                      content={task.result.content}
                      onCiteClick={(index) => {
                        const el = document.getElementById(`source-${index}`);
                        if (el instanceof HTMLDetailsElement) {
                          el.open = true;
                          el.scrollIntoView({ block: "nearest" });
                        }
                      }}
                    />
                  </div>
                  {task.result.citations.length > 0 && (
                    <div className="border-border mt-6 space-y-3 border-t pt-5">
                      <h4 className="text-sm font-medium">{t("原文依据", "Original sources")}</h4>
                      {task.result.citations.map((source) => (
                        <details
                          id={`source-${source.index}`}
                          key={source.index}
                          className="bg-background rounded-xl p-4 text-sm"
                        >
                          <summary className="cursor-pointer leading-6">
                            [{source.index}]{" "}
                            {source.title ||
                              source.document_name ||
                              source.filename ||
                              t("引用资料", "Source")}
                            {source.page || source.page_number
                              ? ` · P${source.page || source.page_number}`
                              : ""}
                          </summary>
                          <blockquote className="border-brand/40 text-muted-foreground mt-3 border-l-2 pl-4 leading-7 whitespace-pre-wrap">
                            {source.quotes?.join("\n\n") || source.content}
                          </blockquote>
                        </details>
                      ))}
                    </div>
                  )}
                </section>
              )}
              <section className="border-border bg-card rounded-2xl border p-5 sm:p-7">
                <h3 className="mb-5 font-semibold">{t("执行记录", "Execution log")}</h3>
                <ol className="space-y-4">
                  {events.map((event) => (
                    <li key={event.seq} className="flex gap-3 text-sm">
                      <span className="bg-brand/50 mt-2 h-1.5 w-1.5 shrink-0 rounded-full" />
                      <div className="min-w-0 flex-1">
                        <p className="break-words">
                          {event.data.message ||
                            (event.kind === "tool_started"
                              ? t("调用工具：", "Calling tool: ")
                              : t("工具返回：", "Tool returned: ")) +
                              ({
                                current_datetime: t("当前时间", "Current time"),
                                ask_user: t("用户澄清", "Ask user"),
                              }[event.data.tool || ""] ||
                                event.data.tool ||
                                "")}
                        </p>
                        {event.kind === "python_result" && (
                          <CodeExecutionPanel result={event.data} zh={zh} />
                        )}
                        <time className="text-muted-foreground mt-1 block text-xs">
                          {new Date(event.created_at).toLocaleTimeString(zh ? "zh-CN" : "en-US")}
                        </time>
                      </div>
                    </li>
                  ))}
                </ol>
                {task.request.tools?.includes("run_python") && (
                  <ArtifactPanel
                    key={task.id}
                    runId={task.id}
                    finished={terminal(task.status)}
                    zh={zh}
                  />
                )}
              </section>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
