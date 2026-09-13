"use client";

import { createContext, useContext, useEffect, useState, useRef } from "react";
import { useLocale } from "next-intl";
import { useAuthStore } from "@/stores";
import { apiClient } from "@/lib/api-client";
import { activateProject, projectStorageKey, type Project } from "@/lib/project-scope";
import { Button } from "@/components/ui";

type Workspace = {
  ready: boolean;
  loading: boolean;
  error: boolean;
  retry: () => void;
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
  const projectList = useRef<Project[]>([]);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!userId) return;
    let active = true;
    setError(false);
    const url = new URL(window.location.href);
    let id = url.searchParams.get("project");
    if (id === null) {
      try {
        id = sessionStorage.getItem(projectStorageKey(userId));
      } catch {
        /* optional */
      }
    }
    const chosen = id && id !== "default" ? id : null;
    const commit = (project: Project | null) => {
      if (!active) return;
      activateProject(userId, project);
      try {
        sessionStorage.setItem(projectStorageKey(userId), project?.id ?? "default");
      } catch {
        /* optional */
      }
      url.searchParams.delete("project");
      window.history.replaceState(window.history.state, "", url);
      setWorkspace((previous) => ({
        project,
        projects: projectList.current.length
          ? projectList.current
          : (previous?.projects ?? (project ? [project] : [])),
      }));
    };
    // Default scope needs no metadata round trip. Named scopes remain gated until
    // the authenticated single-project lookup succeeds; never authorize from cache.
    if (!chosen) commit(null);
    else
      void apiClient
        .get<Project>(`/projects/${chosen}`)
        .then(commit)
        .catch(() => {
          if (active) setError(true);
        });
    setLoading(true);
    void apiClient
      .get<Project[]>("/projects")
      .then((projects) => {
        if (active) {
          projectList.current = projects;
          setWorkspace((previous) => (previous ? { ...previous, projects } : previous));
        }
      })
      .catch(() => {
        if (active) setError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [userId, retry]);

  function switchProject(id: string | null) {
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
  return (
    <Context.Provider
      value={{
        project: workspace?.project ?? null,
        projects: workspace?.projects ?? [],
        ready: !!workspace,
        loading,
        error,
        retry: () => setRetry((v) => v + 1),
        reload,
        switchProject,
      }}
    >
      {children}
    </Context.Provider>
  );
}

/** Mount private page queries only after the selected scope is established. */
export function ProjectContent({ children }: { children: React.ReactNode }) {
  const workspace = useProject();
  const zh = useLocale() === "zh";
  if (workspace?.ready) return <>{children}</>;
  return (
    <div className="space-y-4 p-6" aria-live="polite">
      {workspace?.error ? (
        <>
          <p>
            {zh
              ? "项目暂时无法访问，请重试或切换默认项目。"
              : "Project unavailable. Retry or switch to the default project."}
          </p>
          <Button onClick={workspace.retry}>{zh ? "重试" : "Retry"}</Button>
          <Button variant="outline" onClick={() => workspace.switchProject(null)}>
            {zh ? "默认项目" : "Default project"}
          </Button>
        </>
      ) : (
        <div role="status" className="space-y-4">
          <span className="sr-only">{zh ? "正在恢复工作区" : "Restoring workspace"}</span>
          <div className="bg-muted h-8 w-40 rounded-lg" />
          <div className="bg-muted h-28 max-w-2xl rounded-2xl" />
        </div>
      )}
    </div>
  );
}
