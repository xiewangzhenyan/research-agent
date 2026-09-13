"use client";

import Link from "next/link";
import { useState } from "react";
import { useLocale } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Brain, Check, ChevronDown, FolderOpen, Plus, Settings2 } from "lucide-react";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Input,
  Label,
  Textarea,
} from "@/components/ui";
import { useProject } from "./project-provider";
import { apiClient } from "@/lib/api-client";
import { knowledgeRequest, type KnowledgeBase } from "@/lib/knowledge";
import { type Project } from "@/lib/project-scope";
import { useAuthStore } from "@/stores";

export function ProjectSwitcher() {
  const workspace = useProject();
  const zh = useLocale() === "zh";
  const userId = useAuthStore((s) => s.user?.id);
  const [mode, setMode] = useState<"create" | "edit" | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [ids, setIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const bases = useQuery({
    queryKey: ["knowledge-bases", userId],
    queryFn: () => knowledgeRequest<{ items: KnowledgeBase[] }>("bases"),
    enabled: !!mode && !!userId,
  });
  if (!workspace) return null;
  const { project, projects, reload, switchProject } = workspace;
  const t = (cn: string, en: string) => (zh ? cn : en);
  function open(next: "create" | "edit") {
    setMode(next);
    setName(next === "edit" ? project!.name : "");
    setDescription(next === "edit" ? project!.description : "");
    setIds(next === "edit" ? project!.knowledge_base_ids : []);
    setError("");
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = { name: name.trim(), description: description.trim(), knowledge_base_ids: ids };
      if (mode === "edit") await apiClient.put<Project>(`/projects/${project!.id}`, body);
      else await apiClient.post<Project>("/projects", body);
      await reload();
      setMode(null);
    } catch {
      setError(
        t(
          "保存失败，请检查知识库是否仍可访问后重试。",
          "Save failed. Check knowledge access and retry.",
        ),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className="hover:bg-accent flex h-9 min-w-0 items-center gap-2 rounded-lg border px-2.5 text-sm"
            aria-label={t("切换项目", "Switch project")}
          >
            <FolderOpen className="text-brand h-4 w-4 shrink-0" />
            <span className="max-w-24 truncate sm:max-w-40">
              {project?.name ?? t("默认项目", "Default project")}
            </span>
            <ChevronDown className="h-3 w-3 shrink-0" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-72">
          <DropdownMenuLabel>{t("我的项目", "My projects")}</DropdownMenuLabel>
          <div className="max-h-60 overflow-y-auto">
            {[{ id: null, name: t("默认项目", "Default project") }, ...projects].map((p) => (
              <DropdownMenuItem
                key={p.id ?? "default"}
                onClick={() => p.id !== (project?.id ?? null) && switchProject(p.id)}
                className="gap-2"
              >
                <FolderOpen className="h-4 w-4 shrink-0" />
                <span className="flex-1 truncate">{p.name}</span>
                {p.id === (project?.id ?? null) && <Check className="text-brand h-4 w-4" />}
              </DropdownMenuItem>
            ))}
          </div>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => open("create")}>
            <Plus className="mr-2 h-4 w-4" />
            {t("新建项目", "New project")}
          </DropdownMenuItem>
          {project && (
            <DropdownMenuItem onClick={() => open("edit")}>
              <Settings2 className="mr-2 h-4 w-4" />
              {t("项目设置", "Project settings")}
            </DropdownMenuItem>
          )}
          <DropdownMenuItem asChild>
            <Link href="/memory">
              <Brain className="mr-2 h-4 w-4" />
              {t("项目记忆", "Project memory")}
            </Link>
          </DropdownMenuItem>
          <p className="text-muted-foreground px-2 py-2 text-xs leading-relaxed">
            {t(
              "会话与任务按项目独立保存。知识库属于账号，可跨项目复用。",
              "Chats and tasks are separate per project. Account knowledge bases can be reused across projects.",
            )}
          </p>
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog open={!!mode} onOpenChange={(open) => !open && !busy && setMode(null)}>
        <DialogContent className="flex max-h-[90dvh] w-[calc(100%-1.5rem)] flex-col gap-0 overflow-hidden rounded-2xl p-0 sm:max-w-lg">
          <DialogHeader className="shrink-0 border-b px-6 py-5">
            <DialogTitle>
              {mode === "edit" ? t("项目设置", "Project settings") : t("新建项目", "New project")}
            </DialogTitle>
            <DialogDescription>
              {t(
                "复用账号资料，为不同工作保留独立的会话和任务。",
                "Reuse account resources with separate chats and tasks for each project.",
              )}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={save} className="flex min-h-0 flex-col">
            <div className="space-y-5 overflow-y-auto px-6 py-5">
              <div className="space-y-2">
                <Label htmlFor="project-name">{t("项目名称", "Project name")}</Label>
                <Input
                  id="project-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  maxLength={80}
                  placeholder={t("例如：文献阅读、数据分析", "e.g. Literature review")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="project-description">
                  {t("项目说明（可选）", "Description (optional)")}
                </Label>
                <Textarea
                  id="project-description"
                  rows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={500}
                />
              </div>
              <fieldset className="space-y-3">
                <legend className="text-sm font-medium">
                  {t("默认知识库", "Default knowledge bases")}{" "}
                  <span className="text-muted-foreground">{ids.length}/5</span>
                </legend>
                <p className="text-muted-foreground text-xs leading-relaxed">
                  {t(
                    "新会话和新任务会默认选择这些知识库，仍可单独调整。相同知识库可以用于多个项目，不会复制资料。",
                    "Preselected for new chats and tasks; you can change each selection. Multiple projects can use the same knowledge base without duplicating documents.",
                  )}
                </p>
                {bases.isPending && (
                  <p className="text-sm">{t("正在加载知识库…", "Loading knowledge bases…")}</p>
                )}
                {bases.isError && (
                  <button
                    type="button"
                    className="text-destructive text-sm underline"
                    onClick={() => bases.refetch()}
                  >
                    {t("读取失败，点击重试", "Loading failed. Retry")}
                  </button>
                )}
                {bases.data?.items.length === 0 && (
                  <p className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
                    {t(
                      "还没有知识库。可以先创建项目，之后在知识库页面添加资料。",
                      "No knowledge bases yet. Create the project and add resources later.",
                    )}
                  </p>
                )}
                <div className="space-y-2">
                  {bases.data?.items.map((base) => (
                    <label
                      key={base.id}
                      aria-label={base.name}
                      htmlFor={`project-base-${base.id}`}
                      className="hover:bg-accent flex cursor-pointer items-start gap-3 rounded-xl border p-3 text-sm"
                    >
                      <input
                        id={`project-base-${base.id}`}
                        type="checkbox"
                        className="mt-1 accent-emerald-500"
                        checked={ids.includes(base.id)}
                        disabled={busy || (!ids.includes(base.id) && ids.length >= 5)}
                        onChange={(e) =>
                          setIds(
                            e.target.checked
                              ? [...ids, base.id]
                              : ids.filter((id) => id !== base.id),
                          )
                        }
                      />
                      <span className="min-w-0">
                        <span className="block font-medium break-words">{base.name}</span>
                        <span className="text-muted-foreground text-xs">
                          {base.document_count}{" "}
                          {t("份资料 · 账号知识库", "documents · Account knowledge")}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>
              {error && (
                <p role="alert" className="text-destructive text-sm">
                  {error}
                </p>
              )}
            </div>
            <div className="flex shrink-0 justify-end gap-3 border-t px-6 py-4">
              <Button type="button" variant="outline" disabled={busy} onClick={() => setMode(null)}>
                {t("取消", "Cancel")}
              </Button>
              <Button type="submit" disabled={busy || !name.trim() || bases.isError}>
                {busy ? t("正在保存…", "Saving…") : t("保存", "Save")}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
