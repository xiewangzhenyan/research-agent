import { ApiError } from "@/lib/api-client";
import { currentProject } from "@/lib/project-scope";
import { useAuthStore } from "@/stores/auth-store";

export type MemoryKind = "preference" | "decision" | "constraint" | "note";
export type MemoryItem = {
  id: string;
  project_id: string | null;
  title: string;
  content: string;
  kind: MemoryKind;
  pinned: boolean;
  revision: number;
  source_message_id: string | null;
  expires_on: string | null;
  archived_at: string | null;
  state: "active" | "expired" | "archived";
  index_status: "pending" | "ready" | "failed";
  created_at: string;
  updated_at: string | null;
};
export type MemorySettings = {
  enabled: boolean;
  revision: number;
  auto_extract: boolean;
  semantic_recall: boolean;
  extraction_model: string;
};
export type MemoryProposal = {
  id: string;
  revision: number;
  action: "add" | "update";
  reason: string;
  quote: string;
  source_message_id: string;
  target_id: string | null;
  target_revision: number | null;
  target: MemoryItem | null;
  expires_at: string;
  payload: Pick<
    MemoryItem,
    "title" | "content" | "kind" | "pinned" | "source_message_id" | "expires_on"
  >;
};
export type MemoryJob = {
  id: string;
  status: string;
  attempts: number;
  error: string | null;
  result_count: number;
  created_at: string;
  model: string;
  usage: { input_tokens: number; output_tokens: number } | null;
};
export type MemoryList = MemorySettings & {
  items: MemoryItem[];
  limit: number;
  proposals: MemoryProposal[];
  jobs: MemoryJob[];
  daily_jobs: number;
  daily_limit: number;
};
export type MemoryUsage = {
  retrieval_mode?: "keyword" | "hybrid";
  semantic_status?: string | null;
  status: "used" | "disabled" | "no_match" | "strict_knowledge";
  items: { id: string; revision: number }[];
  omitted: number;
  estimated_tokens: number;
};
export const memoryKey = () => [
  "project-memory",
  useAuthStore.getState().user?.id,
  currentProject()?.id ?? "default",
];
export const kindLabel = (kind: MemoryKind, zh: boolean) =>
  ({
    preference: ["回答偏好", "Preference"],
    decision: ["已确认决策", "Decision"],
    constraint: ["项目约束", "Constraint"],
    note: ["重要笔记", "Note"],
  })[kind][zh ? 0 : 1];
export function memoryError(error: unknown, zh: boolean) {
  if (error instanceof ApiError) {
    const data = error.data as { error?: { message?: string }; detail?: string } | undefined;
    if (zh && (data?.error?.message || typeof data?.detail === "string"))
      return (data?.error?.message || data?.detail) ?? (zh ? "操作失败" : "Request failed");
    if (error.status === 409)
      return zh
        ? "内容已更新或已存在，请刷新后重试。"
        : "Changed or duplicate content. Refresh and retry.";
  }
  return zh ? "操作失败，请稍后重试。" : "Request failed. Please retry.";
}
