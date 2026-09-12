export interface EffectiveConfig {
  model: string;
  temperature: number | null;
  thinking_effort: "low" | "medium" | "high" | null;
  policy_version: string;
}

export interface GenerationModelInfo {
  id: string;
  temperature: boolean;
  thinking_efforts: string[];
  defaults: EffectiveConfig;
  status: "configured" | "unconfigured";
}

export interface LocalModelInfo {
  id: string;
  runtime: string;
  dimension: number | null;
  revision: string | null;
  status: "not_checked" | "healthy" | "unavailable" | "version_mismatch";
  checked_at: string | null;
}

export interface AgentCapabilities {
  default: string;
  policy_version: string;
  models: GenerationModelInfo[];
  embedding: LocalModelInfo;
  rerank: LocalModelInfo;
  capabilities: Array<{ id: string; available: boolean; execution: string }>;
}

export async function fetchCapabilities(signal?: AbortSignal): Promise<AgentCapabilities> {
  const response = await fetch("/api/agent/capabilities", {
    credentials: "include",
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw new Error("模型配置暂时无法加载，请稍后重试。");
  return response.json();
}
