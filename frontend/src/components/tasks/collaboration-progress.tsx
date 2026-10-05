import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  CircleSlash,
  ListTree,
  Loader2,
  PenLine,
  Search,
  ShieldCheck,
} from "lucide-react";

import { cn as cx } from "@/lib/utils";

export type RoleEvent = {
  seq: number;
  kind: string;
  data: {
    role?: string;
    round?: number;
    message?: string;
    queries?: string[];
    issues?: string[];
    approved?: boolean;
    source_count?: number;
  };
};
const roles = [
  ["planner", "plan", "规划", "Plan", ListTree],
  ["researcher", "research", "研究", "Research", Search],
  ["writer", "write", "撰写", "Write", PenLine],
  ["critic", "review", "审校", "Review", ShieldCheck],
] as const;

type CardState = "idle" | "running" | "done" | "attention" | "interrupted";

const STATE_PILL: Record<CardState, string> = {
  idle: "bg-muted text-muted-foreground",
  running: "bg-[color-mix(in_srgb,var(--role)_14%,transparent)] text-[var(--role)]",
  done: "bg-brand/10 text-brand",
  attention: "bg-warning/12 text-warning",
  interrupted: "bg-destructive/10 text-destructive",
};

const STATE_ICON = {
  idle: Circle,
  running: Loader2,
  done: CheckCircle2,
  attention: AlertTriangle,
  interrupted: CircleSlash,
} as const;

export function CollaborationProgress({
  events,
  status,
  zh,
}: {
  events: RoleEvent[];
  status: string;
  zh: boolean;
}) {
  const t = (cn: string, en: string) => (zh ? cn : en);
  const active = ["queued", "running"].includes(status);
  return (
    <section aria-label={t("协作进度", "Collaboration progress")} className="panel p-5 sm:p-6">
      <h3 className="font-semibold">{t("协作进度", "Collaboration progress")}</h3>
      <p className="text-muted-foreground mt-2 text-xs leading-6">
        {t(
          "各阶段按依赖顺序执行，展开查看实际交付与审校意见。",
          "Stages run in dependency order. Expand to inspect their outputs and review findings.",
        )}
      </p>
      <ol className="mt-5 grid gap-3 sm:grid-cols-2">
        {roles.map(([role, tone, cn, en, RoleIcon], index) => {
          const latest = events
            .filter(
              (e) => e.data.role === role && ["role_started", "role_completed"].includes(e.kind),
            )
            .at(-1);
          const complete = latest?.kind === "role_completed";
          const running = !!latest && !complete && active;
          const issue = complete && latest?.data.approved === false;
          const state: CardState = issue
            ? "attention"
            : complete
              ? "done"
              : running
                ? "running"
                : latest
                  ? "interrupted"
                  : "idle";
          const StateIcon = STATE_ICON[state];
          return (
            <li
              key={role}
              data-status={state}
              className={`role-card role-${tone} step-reveal min-w-0 p-4`}
              style={{ animationDelay: `${index * 60}ms` }}
            >
              <div className="flex items-center justify-between gap-2 text-sm">
                <span className="flex items-center gap-2.5 font-medium">
                  <span className="icon-chip h-8 w-8">
                    <RoleIcon size={15} strokeWidth={2} aria-hidden />
                  </span>
                  <span>
                    <span className="block">{t(cn, en)}</span>
                    <span className="text-subtle text-2xs block font-mono">0{index + 1}</span>
                  </span>
                </span>
                <span
                  className={cx(
                    "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs",
                    STATE_PILL[state],
                  )}
                >
                  <StateIcon
                    aria-hidden
                    className={cx("h-3 w-3", state === "running" && "animate-spin")}
                  />
                  {issue
                    ? t("有待解决项", "Issues found")
                    : complete
                      ? t("已完成", "Completed")
                      : running
                        ? t("执行中", "Running")
                        : latest
                          ? t("已中断", "Interrupted")
                          : t("未执行", "Not started")}
                </span>
              </div>
              {!!latest?.data.round && (
                <p className="mt-3">
                  <span className="border-border text-muted-foreground text-2xs inline-flex rounded-full border px-2 py-0.5">
                    {t("修订轮次", "Revision")} {latest.data.round}
                  </span>
                </p>
              )}
              {latest && (
                <details className="mt-3 text-sm">
                  <summary className="text-muted-foreground hover:text-foreground cursor-pointer py-1 text-xs">
                    {t("查看阶段记录", "Stage details")}
                  </summary>
                  <p className="mt-2 leading-6 break-words whitespace-pre-wrap">
                    {latest.data.message}
                  </p>
                  {latest.data.queries && (
                    <ul className="mt-2 list-inside list-disc space-y-2 break-words">
                      {latest.data.queries.map((q, i) => (
                        <li key={i}>{q}</li>
                      ))}
                    </ul>
                  )}
                  {latest.data.source_count !== undefined && (
                    <p className="mt-2">
                      {t("收集原文片段：", "Source passages: ")}
                      {latest.data.source_count}
                    </p>
                  )}
                  {latest.data.issues && (
                    <ul className="mt-2 list-inside list-disc space-y-2 break-words">
                      {latest.data.issues.map((q, i) => (
                        <li key={i}>{q}</li>
                      ))}
                    </ul>
                  )}
                </details>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
