"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useLocale } from "next-intl";
import { useAuthStore, useChatStore } from "@/stores";
import { apiClient } from "@/lib/api-client";
import { activateProject, projectStorageKey, type Project } from "@/lib/project-scope";
import { Button } from "@/components/ui";

type Workspace = {
  project: Project | null;
  projects: Project[];
  reload: () => Promise<void>;
  switchProject: (id: string | null) => void;
};
const Context = createContext<Workspace | null>(null);
export const useProject = () => useContext(Context);

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const userId = useAuthStore((s) => s.user?.id);
  return (
    <Boundary key={userId} userId={userId}>
      {children}
    </Boundary>
  );
}

function Boundary({ userId, children }: { userId?: string; children: React.ReactNode }) {
  const zh = useLocale() === "zh";
  const [workspace, setWorkspace] = useState<{
    project: Project | null;
    projects: Project[];
  } | null>(null);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!userId) return;
    let active = true;
    setError(false);
    apiClient
      .get<Project[]>("/projects")
      .then((projects) => {
        if (!active) return;
        const url = new URL(window.location.href);
        let id = url.searchParams.get("project");
        if (id === null) {
          try {
            id = sessionStorage.getItem(projectStorageKey(userId));
          } catch {
            /* Storage may be disabled. */
          }
        }
        const project = id && id !== "default" ? projects.find((p) => p.id === id) : null;
        if (id && id !== "default" && !project) throw new Error("Project unavailable");
        activateProject(userId, project ?? null);
        try {
          sessionStorage.setItem(projectStorageKey(userId), project?.id ?? "default");
        } catch {
          /* Current document still works. */
        }
        url.searchParams.delete("project");
        window.history.replaceState(window.history.state, "", url);
        setWorkspace({ project: project ?? null, projects });
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [userId, retry]);

  function switchProject(id: string | null) {
    if (
      useChatStore.getState().isStreaming &&
      !window.confirm(
        zh
          ? "回答正在生成，切换项目将中止本次回答。是否继续？"
          : "Switching projects will stop the current answer. Continue?",
      )
    )
      return;
    const url = new URL(window.location.href);
    // A real navigation disposes sockets, callbacks and caches. Commit selection in
    // the next document only, so cancelling beforeunload cannot change this tab's scope.
    url.pathname = `/${zh ? "zh" : "en"}/chat`;
    url.search = "";
    url.hash = "";
    url.searchParams.set("project", id ?? "default");
    window.location.assign(url);
  }
  async function reload() {
    if (!workspace || !userId) return;
    const projects = await apiClient.get<Project[]>("/projects");
    const project = projects.find((p) => p.id === workspace.project?.id) ?? null;
    activateProject(userId, project);
    setWorkspace({ project, projects });
  }
  if (!workspace)
    return (
      <main
        className="flex min-h-dvh flex-col items-center justify-center gap-4 p-6"
        aria-live="polite"
      >
        <p>
          {error
            ? zh
              ? "项目加载失败或不可访问，请重试或返回默认项目。"
              : "Project unavailable. Retry or open the default project."
            : zh
              ? "正在加载项目…"
              : "Loading workspace…"}
        </p>
        {error && (
          <div className="flex gap-3">
            <Button onClick={() => setRetry((v) => v + 1)}>{zh ? "重试" : "Retry"}</Button>
            <Button variant="outline" onClick={() => switchProject(null)}>
              {zh ? "默认项目" : "Default project"}
            </Button>
          </div>
        )}
      </main>
    );
  return (
    <Context.Provider value={{ ...workspace, reload, switchProject }}>{children}</Context.Provider>
  );
}
