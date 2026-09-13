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
  created_at: string;
  updated_at: string | null;
};
export type MemoryList = { enabled: boolean; revision: number; items: MemoryItem[]; limit: number };
export type MemoryUsage = {
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
