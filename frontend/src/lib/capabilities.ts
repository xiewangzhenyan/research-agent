import { projectHeaders } from "@/lib/project-scope";
import { refreshAccessToken } from "@/lib/api-client";
import { useAuthStore } from "@/stores";
export type CapabilityKind = "mcp" | "skills";
export type MCPConfig = {
  transport: "streamable-http" | "sse" | "stdio";
  url: string;
  command: string;
  args: string[];
  enabled_tools: string[];
  auto_approved_tools: string[];
};
export type SkillConfig = {
  entry?: string;
  files: { path: string; size: number; sha256: string }[];
};
export type Capability = {
  id: string;
  kind: "mcp" | "skill";
  name: string;
  description: string;
  scope: "personal" | "project" | "system";
  project_id: string | null;
  tags: string[];
  enabled: boolean;
  revision: number;
  has_credentials: boolean;
  config: MCPConfig | SkillConfig;
  catalog: {
    tools?: { name: string; description?: string; inputSchema: object }[];
    resources?: unknown[];
    prompts?: unknown[];
  };
  status: string;
  status_message: string;
  last_tested: string | null;
  published_version: number | null;
  can_edit: boolean;
  can_bind: boolean;
  updated_at: string;
};
export type Bindings = { asset_ids: string[]; revision: string };
export type Availability = {
  credentials_ready: boolean;
  stdio_ready: boolean;
  agent_keys: string[];
};
export type Version = {
  version: number;
  created_at: string;
  digest: string;
  manifest: { name: string; description: string };
};
export const entryTemplate = `---\nname: research-review\ndescription: 在用户需要整理资料、比较结论并保留证据时使用\n---\n\n# 资料整理\n\n1. 明确用户的问题、范围和输出要求。\n2. 使用已授权的资料与工具，区分事实、推断和待验证内容。\n3. 按主题归纳结论，保留来源；资料不足时说明缺口。\n4. 检查结论与原文是否一致，再给出结果。\n`;
export const assetBody = (a: Capability) => ({
  name: a.name,
  description: a.description,
  scope: a.scope,
  tags: a.tags,
  enabled: a.enabled,
  revision: a.revision,
  config: a.config,
});
export const capabilityError = (e: unknown) =>
  e instanceof Error && typeof e.message === "string" ? e.message : "操作失败，请稍后重试";
export const statusLabel = (a: Capability) =>
  ({
    ready: "连接正常",
    untested: "待测试",
    unavailable: "连接不可用",
    draft: "草稿",
    published: `已发布 v${a.published_version}`,
    published_with_draft: `v${a.published_version} · 有未发布修改`,
  })[a.status] ?? a.status;
export async function capabilityFetch(path: string, init: RequestInit = {}) {
  const requestScope = projectHeaders();
  const requestUser = useAuthStore.getState().user?.id;
  const fetcher = () =>
    fetch(`/api/capabilities/${path}`, {
      ...init,
      headers: { ...init.headers, ...requestScope },
    });
  let response = await fetcher();
  if (response.status === 401 && (await refreshAccessToken())) {
    if (requestUser && useAuthStore.getState().user?.id !== requestUser)
      throw new Error("账号已切换，请重新操作");
    response = await fetcher();
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === "string" ? data.detail : "操作失败，请检查填写内容");
  }
  return response;
}
export async function downloadSkill(id: string) {
  const response = await capabilityFetch(`assets/${id}/export`);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = `skill-${id}.zip`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
