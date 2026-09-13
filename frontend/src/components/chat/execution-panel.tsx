"use client";

import { useEffect, useState } from "react";
import { useLocale } from "next-intl";
import { useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { Button, Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui";
import { useProject } from "@/components/projects/project-provider";
import { ArtifactPanel } from "@/components/tasks/artifact-panel";
import { CodeExecutionPanel } from "@/components/tasks/code-execution-panel";
import { CollaborationProgress } from "@/components/tasks/collaboration-progress";
import { RetrievalSnapshotPanel } from "@/components/tasks/retrieval-settings";
import { MarkdownContent } from "./markdown-content";
import { apiClient, ApiError } from "@/lib/api-client";
import {
  executionFinished,
  executionIdPattern,
  type Execution,
  type ExecutionEvent,
} from "@/lib/execution-details";
import { setUrlParam } from "@/lib/utils";
import { useAuthStore, useConversationStore } from "@/stores";

type Snapshot = { run: Execution; events: ExecutionEvent[]; cursor: number; truncated: boolean };
const accessDenied = (error: unknown) =>
  error instanceof ApiError && [401, 403, 404].includes(error.status);

/** Mounted only in chat. Closing the drawer aborts reads, never server execution. */
export function ExecutionPanel() {
  const search = useSearchParams();
  const runId = search.get("run");
  const userId = useAuthStore((s) => s.user?.id);
  const projectId = useProject()?.project?.id;
  const zh = useLocale() === "zh";
  const close = () => setUrlParam("run", null);
  return (
    <Sheet
      open={!!runId}
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <SheetContent side="right" className="w-full max-w-full sm:w-[560px]">
        <SheetHeader>
          <SheetTitle>{zh ? "执行详情与文件" : "Execution details and files"}</SheetTitle>
          <Button
            variant="ghost"
            size="icon"
            aria-label={zh ? "关闭详情" : "Close details"}
            onClick={close}
          >
            <X className="h-5 w-5" />
          </Button>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 sm:p-5">
          {runId && executionIdPattern.test(runId) && userId ? (
            <ExecutionContent key={`${userId}:${projectId}:${runId}`} runId={runId} close={close} />
          ) : (
            <p role="alert">
              {zh
                ? "记录链接无效，请从对应回答重新打开。"
                : "Invalid link. Open details from the answer."}
            </p>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function ExecutionContent({ runId, close }: { runId: string; close: () => void }) {
  const zh = useLocale() === "zh";
  const t = (cn: string, en: string) => (zh ? cn : en);
  const userId = useAuthStore((s) => s.user?.id);
  const projectId = useProject()?.project?.id;
  const client = useQueryClient();
  const search = useSearchParams();
  const conversationId = search.get("id");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = ["chat-execution-detail", userId, projectId, runId];
  const query = useQuery<Snapshot>({
    queryKey: key,
    enabled: !!userId,
    gcTime: 0,
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchIntervalInBackground: false,
    retry: (count, error) => !accessDenied(error) && count < 1,
    refetchInterval: (q) =>
      accessDenied(q.state.error) ||
      (conversationId &&
        q.state.data?.run.conversation_id &&
        conversationId !== q.state.data.run.conversation_id) ||
      (q.state.data &&
        executionFinished(q.state.data.run.status) &&
        q.state.data.cursor >= q.state.data.run.event_seq)
        ? false
        : 2000,
    queryFn: async ({ signal }): Promise<Snapshot> => {
      const run = await apiClient.get<Execution>(`/tasks/${runId}`, { signal });
      if (conversationId && run.conversation_id && conversationId !== run.conversation_id)
        return { run, events: [], cursor: 0, truncated: false };
      const previous = client.getQueryData<Snapshot>(key);
      let cursor = previous?.cursor ?? 0;
      let events = previous?.events ?? [];
      let truncated = previous?.truncated ?? false;
      // Bound one poll, then continue from its cursor if more events remain.
      for (let page = 0; page < 10 && (page === 0 || cursor < run.event_seq); page++) {
        const next = await apiClient.get<ExecutionEvent[]>(
          `/tasks/${runId}/events?after=${cursor}`,
          { signal },
        );
        const last = next.at(-1)?.seq;
        if (!last || last <= cursor) break;
        events = [...events, ...next];
        truncated ||= events.length > 1000;
        events = events.slice(-1000);
        cursor = last;
        if (next.length < 100) break;
      }
      return { run, events, cursor, truncated };
    },
  });
  const denied = accessDenied(query.error);
  const run = denied ? undefined : query.data?.run;
  const events = query.data?.events ?? [];
  const mismatch = !!(
    conversationId &&
    run?.conversation_id &&
    conversationId !== run.conversation_id
  );
  useEffect(() => {
    if (!run?.conversation_id || conversationId || denied) return;
    // A legacy /tasks?id link has a run id, never a client-supplied conversation scope.
    useConversationStore.getState().setCurrentConversationId(run.conversation_id);
    setUrlParam("new", null);
    setUrlParam("id", run.conversation_id);
  }, [run?.conversation_id, conversationId, denied]);

  async function action(kind: "cancel" | "resume", answers?: Record<string, string[]>) {
    if (!run || busy) return;
    setBusy(true);
    setError("");
    try {
      await apiClient.post(
        `/tasks/${runId}/${kind}`,
        kind === "resume" ? { question_id: run.pending_input?.question_id, answers } : {},
      );
      await Promise.all([
        // A response can arrive after the drawer closes. Only refresh active viewers.
        client.invalidateQueries({ queryKey: key }),
        client.invalidateQueries({
          queryKey: ["chat-runs", userId, projectId, run.conversation_id],
        }),
        client.invalidateQueries({
          queryKey: ["chat-history", userId, projectId, run.conversation_id],
        }),
      ]);
    } catch {
      setError(t("操作未确认，请重试。", "Action not confirmed. Please retry."));
    } finally {
      setBusy(false);
    }
  }
  if (denied || mismatch)
    return (
      <p role="alert">
        {t(
          "此记录不存在、无权访问，或不属于当前会话。",
          "This record is unavailable or belongs to a different conversation.",
        )}
      </p>
    );
  if (!run)
    return query.isError ? (
      <Button variant="outline" onClick={() => query.refetch()}>
        {t("读取失败，点击重试", "Retry loading")}
      </Button>
    ) : (
      <p role="status" className="text-muted-foreground text-sm">
        {t("正在读取执行详情…", "Loading execution details…")}
      </p>
    );
  const labels: Record<string, string> = {
    queued: t("排队中", "Queued"),
    running: t("执行中", "Running"),
    waiting_input: t("待补充信息", "Needs input"),
    cancelling: t("正在停止", "Stopping"),
    cancelled: t("已停止", "Stopped"),
    completed: t("已完成", "Completed"),
    failed: t("执行失败", "Failed"),
  };
  const finished = executionFinished(run.status);
  const legacy = !run.conversation_id;
  const records =
    run.result?.retrieval_runs ??
    events.flatMap((e) =>
      e.kind === "retrieval_completed" && e.data.retrieval ? [e.data.retrieval] : [],
    );
  return (
    <div className="min-w-0 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span role="status" className="text-brand text-sm font-medium">
          {labels[run.status] ?? run.status}
        </span>
        {!finished && (
          <Button
            size="sm"
            variant="outline"
            disabled={busy || run.status === "cancelling"}
            onClick={() => action("cancel")}
          >
            {t("停止此条", "Stop this response")}
          </Button>
        )}
      </div>
      <p className="text-sm leading-7 break-words whitespace-pre-wrap">{run.request.prompt}</p>
      {legacy && (
        <p className="text-muted-foreground text-xs">
          {t(
            "这是一条早期记录，原内容与生成文件仍可查看。",
            "This earlier record retains its original result and files.",
          )}
        </p>
      )}
      {(query.isError || error || run.error) && (
        <p role="alert" className="text-destructive text-sm">
          {error || run.error || t("同步暂时中断，正在重试。", "Sync interrupted. Retrying.")}
        </p>
      )}
      {run.request.tools?.includes("run_python") && (
        <ArtifactPanel runId={run.id} finished={finished} zh={zh} />
      )}
      {run.status === "waiting_input" &&
        run.pending_input &&
        (legacy ? (
          <LegacyQuestions
            key={run.pending_input.question_id}
            pending={run.pending_input}
            busy={busy}
            submit={(answers) => action("resume", answers)}
            zh={zh}
          />
        ) : (
          <Button variant="outline" onClick={close}>
            {t("回到对话补充信息", "Answer in conversation")}
          </Button>
        ))}
      {(run.request.mode === "knowledge_collaboration" ||
        run.request.routing?.route === "knowledge_collaboration" ||
        events.some((e) => e.kind === "role_started")) && (
        <CollaborationProgress events={events} status={run.status} zh={zh} />
      )}
      {legacy && run.result && (
        <section className="space-y-3 rounded-xl border p-4">
          <h3 className="text-sm font-medium">{t("已保存的回答", "Saved answer")}</h3>
          <div className="min-w-0 overflow-x-auto break-words">
            <MarkdownContent
              content={run.result.content}
              onCiteClick={(index) => {
                const source = document.getElementById(`execution-${run.id}-source-${index}`);
                if (source instanceof HTMLDetailsElement) {
                  source.open = true;
                  source.scrollIntoView({ block: "nearest" });
                }
              }}
            />
          </div>
          {run.result.citations?.map((source) => (
            <details
              id={`execution-${run.id}-source-${source.index}`}
              key={source.index}
              className="rounded-lg border p-3 text-sm"
            >
              <summary className="cursor-pointer">
                [{source.index}]{" "}
                {source.title || source.document_name || source.filename || t("原文依据", "Source")}
                {source.page || source.page_number
                  ? ` · P${source.page || source.page_number}`
                  : ""}
              </summary>
              <blockquote className="mt-3 leading-7 break-words whitespace-pre-wrap">
                {source.quotes?.join("\n\n") || source.content}
              </blockquote>
            </details>
          ))}
        </section>
      )}
      <details className="rounded-xl border p-4 text-sm">
        <summary className="cursor-pointer">{t("执行步骤", "Execution steps")}</summary>
        {query.data?.truncated && (
          <p className="text-muted-foreground mt-3 text-xs">
            {t("仅展示最近 1000 条步骤。", "Showing the most recent 1,000 steps.")}
          </p>
        )}
        <ol className="mt-4 space-y-4">
          {events.map((event) => (
            <li key={event.seq} className="min-w-0">
              <p className="leading-6 break-words">
                {event.data.message || event.data.tool || t("状态已更新", "Status updated")}
              </p>
              {event.kind === "python_result" && <CodeExecutionPanel result={event.data} zh={zh} />}
              <time className="text-muted-foreground text-xs">
                {new Date(event.created_at).toLocaleTimeString(zh ? "zh-CN" : "en-US")}
              </time>
            </li>
          ))}
        </ol>
      </details>
      {!!run.request.knowledge_base_ids?.length && (
        <RetrievalSnapshotPanel
          snapshot={run.request.retrieval_snapshot}
          records={records}
          zh={zh}
        />
      )}
      <details className="text-muted-foreground rounded-xl border p-4 text-xs">
        <summary className="cursor-pointer py-1">
          {t("本次配置", "Execution settings")} · {run.effective_config.model}
        </summary>
        <p className="mt-3 leading-6 break-all">
          {t("执行次数", "Attempts")}: {run.attempt}
          <br />
          {t("已授权工具", "Allowed tools")}: {run.request.tools?.join(", ") || t("无", "None")}
          <br />
          {t("推理强度", "Reasoning")}:{" "}
          {run.effective_config.thinking_effort ?? t("模型默认", "Model default")} ·{" "}
          {t("温度", "Temperature")}:{" "}
          {run.effective_config.temperature ?? t("模型默认", "Model default")}
        </p>
      </details>
    </div>
  );
}

function LegacyQuestions({
  pending,
  busy,
  submit,
  zh,
}: {
  pending: NonNullable<Execution["pending_input"]>;
  busy: boolean;
  submit: (answers: Record<string, string[]>) => void;
  zh: boolean;
}) {
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const complete = pending.calls.every((c) =>
    c.questions.every((_, i) => answers[c.call_id]?.[i]?.trim()),
  );
  return (
    <form
      className="space-y-4 rounded-xl border p-4"
      onSubmit={(e) => {
        e.preventDefault();
        submit(answers);
      }}
    >
      <h3 className="text-sm font-medium">
        {zh ? "补充信息后继续" : "Provide details to continue"}
      </h3>
      {pending.calls.flatMap((call) =>
        call.questions.map((q, i) => (
          <label key={`${call.call_id}:${i}`} className="block space-y-2 text-sm">
            <span>{q.question}</span>
            {!!q.options?.length && (
              <span className="text-muted-foreground block text-xs">{q.options.join(" / ")}</span>
            )}
            <textarea
              required
              maxLength={2000}
              disabled={busy}
              value={answers[call.call_id]?.[i] ?? ""}
              className="w-full rounded-lg border p-3"
              onChange={(e) =>
                setAnswers((previous) => {
                  const values = [...(previous[call.call_id] ?? call.questions.map(() => ""))];
                  values[i] = e.target.value;
                  return { ...previous, [call.call_id]: values };
                })
              }
            />
          </label>
        )),
      )}
      <Button disabled={busy || !complete}>{zh ? "保存并继续" : "Save and continue"}</Button>
    </form>
  );
}
