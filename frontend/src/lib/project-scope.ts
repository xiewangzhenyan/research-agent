import { useAuthStore } from "@/stores/auth-store";

export type Project = {
  id: string;
  name: string;
  description: string;
  knowledge_base_ids: string[];
};

// Set only after the workspace boundary has authenticated and validated selection.
// Never persist a project in a shared cookie: different tabs may use different projects.
let scope: { userId: string; project: Project | null } | null = null;
export const projectStorageKey = (userId: string) => `research-agent:project:${userId}`;
export function activateProject(userId: string, project: Project | null) {
  scope = { userId, project };
}
export function currentProject() {
  return scope?.userId === useAuthStore.getState().user?.id ? (scope?.project ?? null) : null;
}
export function projectHeaders(): Record<string, string> {
  const id = currentProject()?.id;
  return id ? { "X-Project-ID": id } : {};
}
export function projectFetch(input: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  const id = currentProject()?.id;
  if (id) headers.set("X-Project-ID", id);
  else headers.delete("X-Project-ID");
  return fetch(input, { ...init, headers });
}
