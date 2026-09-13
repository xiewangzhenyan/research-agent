"use client";
import Link from "next/link";
import { useLocale } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Check,
  LockKeyhole,
  RefreshCw,
  Terminal,
  Timer,
  ShieldCheck,
  ArrowUpRight,
} from "lucide-react";
import { PageHeader } from "@/components/dashboard/page-header";
import { Button } from "@/components/ui";
import { useAuthStore } from "@/stores";
import { fetchTools } from "@/lib/tool-catalog";

export default function ToolsPage() {
  const zh = useLocale() === "zh";
  const t = (cn: string, en: string) => (zh ? cn : en);
  const user = useAuthStore((s) => s.user);
  const query = useQuery({
    queryKey: ["tools", user?.id],
    queryFn: ({ signal }) => fetchTools(signal),
    enabled: !!user,
    staleTime: 15000,
  });
  const labels: Record<string, string> = {
    current_datetime: t("当前时间", "Current time"),
    ask_user: t("用户澄清", "Ask user"),
    run_python: t("Python 计算", "Python execution"),
  };
  return (
    <div className="tools-workspace space-y-6 pb-8">
      <PageHeader
        eyebrow={t("能力与权限", "TOOLS & PERMISSIONS")}
        title={t("工具中心", "Tools")}
        description={t(
          "查看可用工具与执行边界，在创建任务时按需授权。",
          "Inspect available tools and choose permissions when creating a task.",
        )}
        actions={
          <Button variant="outline" disabled={query.isFetching} onClick={() => query.refetch()}>
            <RefreshCw size={15} className="mr-2" />
            {t("刷新状态", "Refresh")}
          </Button>
        }
      />
      {query.isPending && (
        <p role="status" className="text-muted-foreground py-8">
          {t("正在读取工具配置…", "Loading tools…")}
        </p>
      )}
      {query.isError && (
        <p role="alert" className="border-destructive/30 bg-destructive/5 rounded-xl border p-5">
          {t("工具加载失败，请刷新重试。", "Tools unavailable. Refresh to retry.")}
        </p>
      )}
      {query.data && (
        <>
          <section className="grid gap-4 lg:grid-cols-3">
            {query.data.items.map((item) => (
              <article
                key={item.id}
                className="border-border bg-card flex flex-col rounded-2xl border p-5 sm:p-6"
              >
                <div className="mb-4 flex items-center justify-between gap-3">
                  <span className="text-brand bg-brand/10 rounded-xl p-3">
                    <Terminal size={20} />
                  </span>
                  <span
                    className={`flex items-center gap-1.5 text-xs ${item.available ? "text-brand" : "text-muted-foreground"}`}
                  >
                    {item.available ? <Check size={14} /> : <LockKeyhole size={14} />}
                    {item.available ? t("可使用", "Available") : t("未开放", "Unavailable")}
                  </span>
                </div>
                <h2 className="text-lg font-semibold">{labels[item.id] || item.id}</h2>
                <p className="text-muted-foreground mt-2 min-h-12 text-sm leading-6">
                  {zh
                    ? item.description
                    : (
                        {
                          current_datetime: "Read the server date and time.",
                          ask_user: "Pause and ask for missing information.",
                          run_python:
                            "Execute Python standard-library code in an isolated environment with no network.",
                        } as Record<string, string>
                      )[item.id]}
                </p>
                <dl className="border-border mt-5 space-y-3 border-t pt-4 text-sm">
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted-foreground">{t("执行位置", "Execution")}</dt>
                    <dd>
                      {item.execution === "sandbox"
                        ? t("独立沙箱", "Isolated sandbox")
                        : item.execution === "interaction"
                          ? t("交互与暂停", "Human interaction")
                          : t("应用服务", "Application")}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted-foreground">{t("最长执行时间", "Time limit")}</dt>
                    <dd>
                      {item.timeout_seconds
                        ? `${item.timeout_seconds} ${t("秒", "sec")}`
                        : t("等待用户补充", "Wait for input")}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted-foreground">{t("输出上限", "Output limit")}</dt>
                    <dd>{Math.round(item.output_limit_bytes / 1024)} KB</dd>
                  </div>
                </dl>
                {!item.available && (
                  <p className="text-muted-foreground bg-background mt-5 rounded-lg p-3 text-xs leading-6">
                    {zh
                      ? item.reason
                      : t("", "The isolated runtime is not ready or your account is not eligible.")}
                  </p>
                )}
              </article>
            ))}
          </section>
          <section className="border-border bg-card rounded-2xl border p-5 sm:p-6">
            <div className="flex items-start gap-3">
              <ShieldCheck className="text-brand mt-1 shrink-0" size={22} />
              <div>
                <h2 className="text-lg font-semibold">
                  {t("代码执行环境", "Code execution environment")}
                </h2>
                <p className="text-muted-foreground mt-2 text-sm leading-7">
                  {query.data.sandbox.status === "ready"
                    ? t(
                        "隔离节点已连接。是否可执行代码仍取决于账号权限与本次任务的授权。",
                        "The isolated node is connected. Account policy and task permissions still apply.",
                      )
                    : t(
                        "独立沙箱尚未就绪，当前不会在业务服务器执行代码。时间查询、用户澄清与知识库问答可正常使用。",
                        "The isolated runtime is not ready. Code will not run on the application server; existing tools and knowledge answers remain available.",
                      )}
                </p>
              </div>
            </div>
            <div className="mt-5 grid gap-3 text-sm sm:grid-cols-3">
              {[
                t("默认禁网，不注入业务密钥", "No network or application secrets"),
                t("独立工作区，不跨任务共享", "Separate workspace per execution"),
                t("超时停止，确认退出后更新状态", "Stop and confirm exit on timeout"),
              ].map((text) => (
                <p
                  key={text}
                  className="border-border flex items-start gap-2 rounded-xl border p-3"
                >
                  <Timer size={16} className="text-brand mt-0.5 shrink-0" />
                  {text}
                </p>
              ))}
            </div>
            <p className="text-muted-foreground mt-4 text-xs leading-6">
              {query.data.sandbox.file_execution
                ? t(
                    "文件执行已就绪：支持 NumPy、pandas 和 Matplotlib；最多 5 个只读输入（合计 5 MiB），生成文件单个 2 MiB、合计 4 MiB，可在回答的执行详情中下载。",
                    "File execution is ready: NumPy, pandas and Matplotlib; up to 5 read-only inputs (5 MiB total), generated files up to 2 MiB each / 4 MiB total, downloadable from the answer details.",
                  )
                : query.data.sandbox.status === "ready"
                  ? t(
                      "当前节点提供标准库与文本输出，文件功能需要升级执行节点。",
                      "This node provides standard-library execution and text output. File support requires a node upgrade.",
                    )
                  : t(
                      "文件执行版本支持只读输入、数据分析和生成文件下载，需独立执行节点通过验证后开放。",
                      "The file execution version supports read-only inputs, data analysis and downloads, pending validation of an independent execution node.",
                    )}
            </p>
          </section>
          <div className="text-muted-foreground flex flex-wrap items-center justify-between gap-3 text-xs">
            <span>
              {t("工具策略版本：", "Policy: ")}
              {query.data.version}
            </span>
            <Link href="/chat?new=1" className="text-brand inline-flex min-h-10 items-center gap-1">
              {t("在对话中使用工具", "Use tools in chat")}
              <ArrowUpRight size={14} />
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
