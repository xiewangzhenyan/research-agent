"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Download, ListChecks, Pause, Play } from "lucide-react";
import { apiClient, ApiError } from "@/lib/api-client";
import { currentProject } from "@/lib/project-scope";
import { useAuthStore } from "@/stores";
import { useFileDownload } from "@/hooks/use-file-download";
import type { WorkTask, WorkTaskSelection } from "@/lib/chat-turns";

const labels = { active: "进行中", paused: "已暂停", cancelled: "已取消", completed: "已完成" };
const executing = (status?: string) =>
  !!status && ["queued", "running", "waiting_input", "cancelling"].includes(status);
const button = "hover:bg-muted min-h-10 rounded-lg px-3 text-xs disabled:opacity-40";
type Send = (message: string, selection: WorkTaskSelection) => boolean;

export function WorkTaskPanel({
  conversationId,
  onSend,
  disabled,
}: {
  conversationId: string | null;
  onSend: Send;
  disabled: boolean;
}) {
  const userId = useAuthStore((s) => s.user?.id);
  const projectId = currentProject()?.id;
  return (
    <TaskScope
      key={`${userId}:${projectId}:${conversationId}`}
      userId={userId}
      projectId={projectId}
      conversationId={conversationId}
      onSend={onSend}
      disabled={disabled}
    />
  );
}

function TaskScope({
  userId,
  projectId,
  conversationId,
  onSend,
  disabled,
}: {
  userId?: string;
  projectId?: string;
  conversationId: string | null;
  onSend: Send;
  disabled: boolean;
}) {
  const [all, setAll] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const query = useQuery({
    queryKey: ["work-tasks", userId, projectId, "list", all ? null : conversationId],
    queryFn: ({ signal }) =>
      apiClient.get<{ items: WorkTask[] }>(
        `/chat/work-tasks${conversationId && !all ? `?conversation_id=${conversationId}` : ""}`,
        { signal },
      ),
    enabled: !!userId,
    staleTime: 10000,
    refetchInterval: (q) =>
      q.state.data?.items?.some((t) => executing(t.steps[0]?.status)) ? 5000 : 30000,
    refetchIntervalInBackground: false,
    retry: (count, error) =>
      !(error instanceof ApiError && [401, 403, 404].includes(error.status)) && count < 1,
  });
  const tasks = query.data?.items ?? [];
  if (!tasks.length && !conversationId && !query.isError) return null;
  return (
    <section
      aria-label="工作任务"
      className="border-border/70 bg-muted/15 mb-4 rounded-2xl border text-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-x-2 px-3">
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
          className="flex min-h-11 min-w-0 items-center gap-2 text-left"
        >
          <ListChecks aria-hidden className="text-muted-foreground h-4 w-4 shrink-0" />
          <span>{tasks.length ? `工作任务 · ${tasks.length}` : "续接工作任务"}</span>
          <ChevronDown aria-hidden className={`h-4 w-4 ${expanded ? "rotate-180" : ""}`} />
        </button>
        {conversationId && (
          <button
            type="button"
            className={button + " text-muted-foreground"}
            onClick={() => {
              setAll(!all);
              setExpanded(true);
            }}
          >
            {all ? "返回本会话" : "查看项目近期任务"}
          </button>
        )}
      </div>
      {expanded && (
        <div className="space-y-2 px-3 pb-3">
          {query.isError ? (
            <p role="alert" className="text-muted-foreground">
              任务进度暂时无法同步。
              <button type="button" className={button} onClick={() => void query.refetch()}>
                重试
              </button>
            </p>
          ) : query.isPending ? (
            <p className="text-muted-foreground py-2">正在读取任务…</p>
          ) : !tasks.length ? (
            <p className="text-muted-foreground py-2">
              本会话还没有工作任务。发送“创建任务：”及完整目标即可开始。
            </p>
          ) : (
            tasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                userId={userId}
                projectId={projectId}
                onSend={onSend}
                disabled={disabled}
              />
            ))
          )}
          {!!tasks.length && (
            <p className="text-muted-foreground px-1 pt-1 text-xs">
              显示最近 20 个任务。进度随执行保存，可在同一项目的新对话中续做。
            </p>
          )}
        </div>
      )}
    </section>
  );
}

export function TaskCard({
  task,
  userId,
  projectId,
  onSend,
  disabled,
}: {
  task: WorkTask;
  userId?: string;
  projectId?: string;
  onSend: Send;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<"revise" | "replace" | null>(null);
  const [draft, setDraft] = useState("");
  // Pin the version at edit start: a second window must not silently overwrite it.
  const [editRevision, setEditRevision] = useState(task.revision);
  const detail = useQuery({
    queryKey: ["work-tasks", userId, projectId, "detail", task.id, task.revision],
    queryFn: ({ signal }) => apiClient.get<WorkTask>(`/chat/work-tasks/${task.id}`, { signal }),
    enabled: open && !!userId,
    staleTime: 5000,
    refetchInterval: open && executing(task.steps[0]?.status) ? 5000 : false,
  });
  const value = detail.data && detail.data.revision >= task.revision ? detail.data : task;
  const { download, busy } = useFileDownload(task.id);
  const send = (action: WorkTaskSelection["action"], text: string, revision = value.revision) =>
    onSend(text, { action, task_id: task.id, expected_revision: revision });
  const edit = (action: "revise" | "replace") => {
    setEditing(action);
    setEditRevision(value.revision);
    setDraft("");
  };
  const active = value.steps.some((step) => executing(step.status));
  return (
    <article className="border-border/60 bg-background/60 rounded-xl border p-3">
      <div className="flex items-start gap-2">
        <h3 className="min-w-0 flex-1 text-sm font-medium break-words">{value.title}</h3>
        <span className="text-muted-foreground shrink-0 pt-0.5 text-xs">
          {labels[value.status]} · v{value.revision}
        </span>
      </div>
      <p className="text-muted-foreground mt-1 text-xs" aria-live="polite">
        {active ? value.steps.find((s) => executing(s.status))?.phase : value.next_action}
      </p>
      {!value.source_valid && (
        <p role="alert" className="mt-2 text-xs">
          原始要求已修改或删除，请重新设定完整目标。
        </p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-1">
        <button
          type="button"
          className={button + " inline-flex items-center gap-1"}
          disabled={disabled || !value.source_valid || active}
          onClick={() => send("continue", "继续之前的任务")}
        >
          <Play className="h-3 w-3" />
          继续
        </button>
        {value.status === "active" && (
          <button
            type="button"
            className={button + " inline-flex items-center gap-1"}
            disabled={disabled}
            onClick={() => send("pause", "暂停当前任务")}
          >
            <Pause className="h-3 w-3" />
            暂停
          </button>
        )}
        <button
          type="button"
          className={button}
          disabled={disabled}
          onClick={() => edit(value.source_valid ? "revise" : "replace")}
        >
          {value.source_valid ? "调整要求" : "重新设定目标"}
        </button>
        <button
          type="button"
          className={button + " text-muted-foreground"}
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          {open ? "收起详情" : "要求与执行记录"}
        </button>
      </div>
      {editing && (
        <form
          className="mt-3 space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (draft.trim() && send(editing, draft.trim(), editRevision)) setEditing(null);
          }}
        >
          <label className="block text-xs" htmlFor={`task-goal-${task.id}`}>
            {editing === "replace"
              ? "完整新目标（替代原有全部要求）"
              : "追加或修改要求（保留其他原有要求）"}
          </label>
          <textarea
            style={{ outline: "none" }}
            id={`task-goal-${task.id}`}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            maxLength={12000}
            rows={3}
            className="bg-background focus-visible:ring-foreground/20 w-full resize-y rounded-lg border p-3 text-sm outline-none focus-visible:ring-1"
          />
          <div className="flex flex-wrap gap-1">
            <button
              type="submit"
              disabled={disabled || !draft.trim()}
              className={button + " border"}
            >
              保存要求并继续
            </button>
            <button
              type="button"
              className={button}
              disabled={disabled}
              onClick={() => {
                setEditing(editing === "revise" ? "replace" : "revise");
              }}
            >
              {editing === "revise" ? "改为完整替换" : "改为追加修改"}
            </button>
            <button type="button" className={button} onClick={() => setEditing(null)}>
              放弃编辑
            </button>
          </div>
        </form>
      )}
      {open && (
        <div className="mt-3 space-y-3 border-t pt-3 text-xs">
          {detail.isError && (
            <p role="alert">
              执行记录暂时无法读取。
              <button className={button} onClick={() => void detail.refetch()}>
                重试
              </button>
            </p>
          )}
          {detail.isPending ? (
            <p>正在读取记录…</p>
          ) : (
            <>
              <ol className="space-y-2">
                {value.requirements.map((r) => (
                  <li key={r.revision} className="break-words whitespace-pre-wrap">
                    <span className="text-muted-foreground">v{r.revision} · </span>
                    {r.valid ? r.content : "此版本来源已失效"}
                  </li>
                ))}
              </ol>
              <ol aria-label="执行记录" className="space-y-2">
                {value.steps.map((step) => (
                  <li key={step.id}>
                    v{step.revision} · {step.historical ? "历史执行 · " : ""}
                    {step.phase}
                  </li>
                ))}
              </ol>
              <div className="flex flex-wrap gap-2">
                {value.artifacts.map((file) => (
                  <button
                    key={file.id}
                    type="button"
                    disabled={!!busy}
                    className={button + " flex max-w-full items-center gap-2 border text-left"}
                    onClick={() =>
                      download(`/api/tasks/${file.run_id}/artifacts/${file.id}`, file.name)
                    }
                  >
                    <Download className="h-3 w-3 shrink-0" />
                    <span className="break-all">
                      {file.name} · v{file.revision}
                      {file.historical ? "（历史文件）" : ""}
                    </span>
                  </button>
                ))}
              </div>
              <p className="text-muted-foreground">
                本轮返回结果不代表整个任务已验收。此处展示最近 10 次执行及 20
                个文件；删除来源会话后，对应内容和文件不再可用。
              </p>
            </>
          )}
          <div className="flex flex-wrap gap-1">
            {value.status !== "completed" && (
              <button
                type="button"
                disabled={disabled || active}
                className={button + " border"}
                onClick={() => send("complete", "当前任务已完成")}
              >
                标记任务完成
              </button>
            )}
            {value.status !== "cancelled" && value.status !== "completed" && (
              <button
                type="button"
                disabled={disabled}
                className={button}
                onClick={() => send("cancel", "取消当前任务")}
              >
                取消任务
              </button>
            )}
            {!editing && (
              <button
                type="button"
                disabled={disabled}
                className={button}
                onClick={() => edit("replace")}
              >
                重新设定完整目标
              </button>
            )}
          </div>
        </div>
      )}
    </article>
  );
}
