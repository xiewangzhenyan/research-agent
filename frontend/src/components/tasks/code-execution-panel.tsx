"use client";

export type ExecutionResult = {
  code?: string;
  state?: string;
  stdout?: string;
  stderr?: string;
  exit_code?: number;
  truncated?: boolean;
  oom_killed?: boolean;
  error?: string;
  protocol?: number;
};

export function CodeExecutionPanel({
  result,
  zh = true,
}: {
  result: ExecutionResult;
  zh?: boolean;
}) {
  const t = (cn: string, en: string) => (zh ? cn : en);
  const states: Record<string, string> = {
    completed: t("执行完成", "Completed"),
    failed: t("执行失败", "Failed"),
    timed_out: t("执行超时", "Timed out"),
    cancelled: t("已取消", "Cancelled"),
    output_limit: t("输出超限", "Output limit"),
  };
  const ok = result.state === "completed";
  return (
    <details
      className="border-border bg-background mt-3 overflow-hidden rounded-xl border"
      open={!ok}
    >
      <summary className="cursor-pointer px-4 py-3 text-sm font-medium">
        <span className={ok ? "text-brand" : "text-destructive"}>
          {states[result.state || ""] || t("状态未知", "Unknown state")}
        </span>
        <span className="text-muted-foreground ml-3 font-normal">
          {t("代码与输出", "Code and output")} · {t("退出码", "Exit code")}{" "}
          {result.exit_code ?? "—"}
        </span>
      </summary>
      <div className="border-border space-y-4 border-t p-4">
        <p className="text-muted-foreground text-xs">
          {t("无网络 · 独立工作区 · 30 秒上限", "No network · Fresh workspace · 30s limit")} ·{" "}
          {result.protocol === 2 ? "512 MiB" : "256 MiB"}
        </p>
        {result.code && (
          <section>
            <h4 className="text-muted-foreground mb-2 text-xs">Python</h4>
            <pre className="bg-muted/40 max-h-72 overflow-auto rounded-lg p-3 text-xs break-all whitespace-pre-wrap">
              {result.code}
            </pre>
          </section>
        )}
        <section>
          <h4 className="text-muted-foreground mb-2 text-xs">{t("标准输出", "Standard output")}</h4>
          <pre className="max-h-72 overflow-auto text-xs break-all whitespace-pre-wrap">
            {result.stdout || t("无文本输出", "No text output")}
          </pre>
        </section>
        {result.stderr && (
          <section>
            <h4 className="text-destructive mb-2 text-xs">{t("错误输出", "Standard error")}</h4>
            <pre className="text-destructive max-h-72 overflow-auto text-xs break-all whitespace-pre-wrap">
              {result.stderr}
            </pre>
          </section>
        )}
        {result.error && <p className="text-destructive text-xs">{result.error}</p>}
        {result.oom_killed && (
          <p className="text-destructive text-xs">
            {t("执行因内存超限而终止", "Stopped at the memory limit")}
          </p>
        )}
        {result.truncated && (
          <p className="text-destructive text-xs">
            {t(
              "输出超过 32 KiB，已截断并停止执行",
              "Output exceeded 32 KiB; truncated and stopped",
            )}
          </p>
        )}
      </div>
    </details>
  );
}
