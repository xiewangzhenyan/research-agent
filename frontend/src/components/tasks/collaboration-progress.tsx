import { CheckCircle2, Circle, Clock3 } from "lucide-react";

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
  ["planner", "规划", "Plan"],
  ["researcher", "研究", "Research"],
  ["writer", "撰写", "Write"],
  ["critic", "审校", "Review"],
] as const;

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
    <section
      aria-label={t("协作进度", "Collaboration progress")}
      className="border-border bg-card rounded-2xl border p-5 sm:p-7"
    >
      <h3 className="font-semibold">{t("协作进度", "Collaboration progress")}</h3>
      <p className="text-muted-foreground mt-2 text-xs leading-6">
        {t(
          "各阶段按依赖顺序执行，展开查看实际交付与审校意见。",
          "Stages run in dependency order. Expand to inspect their outputs and review findings.",
        )}
      </p>
      <ol className="mt-4 grid gap-3 sm:grid-cols-2">
        {roles.map(([role, cn, en]) => {
          const latest = events
            .filter(
              (e) => e.data.role === role && ["role_started", "role_completed"].includes(e.kind),
            )
            .at(-1);
          const complete = latest?.kind === "role_completed";
          const running = !!latest && !complete && active;
          const issue = complete && latest?.data.approved === false;
          const Icon = complete ? CheckCircle2 : running ? Clock3 : Circle;
          return (
            <li
              key={role}
              className={`min-w-0 rounded-xl border p-4 ${issue ? "border-amber-500/40" : running ? "border-brand/50 bg-brand/5" : "border-border"}`}
            >
              <div className="flex items-center justify-between gap-2 text-sm">
                <span className="flex items-center gap-2 font-medium">
                  <Icon
                    size={16}
                    className={
                      issue
                        ? "text-amber-500"
                        : complete || running
                          ? "text-brand"
                          : "text-muted-foreground"
                    }
                  />
                  {t(cn, en)}
                </span>
                <span className="text-muted-foreground text-xs">
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
                <p className="text-muted-foreground mt-2 text-xs">
                  {t("修订轮次", "Revision")} {latest.data.round}
                </p>
              )}
              {latest && (
                <details className="mt-3 text-sm">
                  <summary className="cursor-pointer py-1 text-xs">
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
