"use client";
import { useLocale } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui";
import { apiClient } from "@/lib/api-client";
interface Health {
  status: string;
  checks: Record<
    string,
    { status: string; latency_ms?: number; detail?: string; provider?: string }
  >;
}
export default function SystemHealthPage() {
  const zh = useLocale() === "zh";
  const query = useQuery({
    queryKey: ["admin", "health"],
    queryFn: () => apiClient.get<Health>("/admin/health"),
    refetchInterval: 30000,
  });
  const labels: Record<string, string> = zh
    ? { database: "数据库", redis: "缓存", llm: "模型服务配置", worker: "后台执行服务配置" }
    : {
        database: "Database",
        redis: "Cache",
        llm: "Model configuration",
        worker: "Worker configuration",
      };
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-xl font-semibold">{zh ? "系统状态" : "System health"}</h2>
        <Button disabled={query.isFetching} onClick={() => query.refetch()}>
          {zh ? "刷新" : "Refresh"}
        </Button>
      </div>
      <p className="text-muted-foreground text-sm">
        {zh
          ? "数据库和缓存为实时检查；模型和后台执行服务仅检查配置，不代表调用成功。"
          : "Database and cache are probed live. Model and worker checks verify configuration only, not successful execution."}
      </p>
      {query.isLoading && <p>{zh ? "检查中…" : "Checking…"}</p>}
      {query.isError && (
        <p role="alert" className="text-destructive">
          {zh ? "状态读取失败，请重试。" : "Could not load health. Please retry."}
        </p>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        {Object.entries(query.data?.checks ?? {}).map(([key, check]) => (
          <div className="space-y-2 rounded-xl border p-5" key={key}>
            <h3 className="font-semibold">{labels[key] ?? key}</h3>
            <p>
              {check.status === "healthy"
                ? key === "llm" || key === "worker"
                  ? zh
                    ? "已配置（未验证连通性）"
                    : "Configured (connectivity not verified)"
                  : zh
                    ? "正常"
                    : "Healthy"
                : zh
                  ? "异常或未知"
                  : "Unhealthy or unknown"}
            </p>
            {typeof check.latency_ms === "number" && (
              <p className="text-muted-foreground text-sm">{check.latency_ms} ms</p>
            )}
            {check.provider && <p className="text-muted-foreground text-sm">{check.provider}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}
