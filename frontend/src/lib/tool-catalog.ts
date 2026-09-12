export type ToolInfo = {
  id: string;
  label: string;
  description: string;
  version: string;
  execution: string;
  available: boolean;
  default_enabled: boolean;
  timeout_seconds: number | null;
  output_limit_bytes: number;
  retry: string;
  reason: string | null;
};
export type ToolCatalog = {
  version: string;
  items: ToolInfo[];
  sandbox: {
    status: string;
    runtime: string;
    network: string;
    file_execution?: {
      input_bytes: number;
      artifact_file_bytes: number;
      artifact_total_bytes: number;
      memory_mb: number;
    };
  };
};
export async function fetchTools(signal?: AbortSignal): Promise<ToolCatalog> {
  const response = await fetch("/api/tasks/tools", {
    signal,
    cache: "no-store",
    credentials: "include",
  });
  if (!response.ok) throw new Error("工具配置加载失败，请稍后重试");
  return response.json();
}
