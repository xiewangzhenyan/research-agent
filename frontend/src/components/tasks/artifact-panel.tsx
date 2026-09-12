"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, FileText, Trash2 } from "lucide-react";
import { useAuthStore } from "@/stores";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

type Artifact = { id: string; name: string; size: number; mime_type: string };
export function ArtifactPanel({
  runId,
  finished,
  zh = true,
}: {
  runId: string;
  finished: boolean;
  zh?: boolean;
}) {
  const userId = useAuthStore((s) => s.user?.id);
  const [error, setError] = useState("");
  const [removing, setRemoving] = useState<Artifact | null>(null);
  const [busy, setBusy] = useState(false);
  const t = (cn: string, en: string) => (zh ? cn : en);
  const query = useQuery({
    queryKey: ["task-artifacts", userId, runId, finished],
    enabled: !!userId,
    refetchInterval: finished ? false : 3000,
    queryFn: async ({ signal }): Promise<Artifact[]> => {
      const response = await fetch(`/api/tasks/${runId}/artifacts`, { signal, cache: "no-store" });
      if (!response.ok) throw new Error(t("产物加载失败", "Failed to load files"));
      return response.json();
    },
  });
  async function remove() {
    if (!removing) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/tasks/${runId}/artifacts/${removing.id}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error(t("删除失败，请稍后重试", "Deletion failed; try again"));
      setRemoving(null);
      await query.refetch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="border-border mt-4 rounded-xl border p-4">
      <h3 className="text-sm font-medium">{t("生成文件", "Generated files")}</h3>
      {query.isError ? (
        <button
          type="button"
          className="text-destructive mt-2 text-xs underline"
          onClick={() => query.refetch()}
        >
          {t("加载失败，点击重试", "Loading failed. Retry")}
        </button>
      ) : !query.data?.length ? (
        <p className="text-muted-foreground mt-2 text-xs">
          {query.isPending
            ? t("正在加载…", "Loading…")
            : t(
                "暂无文件。计算成功并生成产物后将在此显示。",
                "Files appear here after successful generation.",
              )}
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {query.data.map((file) => (
            <li key={file.id} className="bg-muted/40 flex items-center gap-3 rounded-lg p-3">
              <FileText className="text-muted-foreground h-4 w-4 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm">{file.name}</p>
                <p className="text-muted-foreground text-xs">{Math.ceil(file.size / 1024)} KiB</p>
              </div>
              <a
                href={`/api/tasks/${runId}/artifacts/${file.id}`}
                download
                className="text-brand hover:bg-muted rounded-md p-2"
                aria-label={t("下载", "Download") + " " + file.name}
              >
                <Download className="h-4 w-4" />
              </a>
              {finished && (
                <button
                  type="button"
                  className="text-muted-foreground hover:text-destructive rounded-md p-2"
                  aria-label={t("删除", "Delete") + " " + file.name}
                  onClick={() => setRemoving(file)}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p role="alert" className="text-destructive mt-2 text-xs">
          {error}
        </p>
      )}
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(open) => !busy && !open && setRemoving(null)}
        title={t("删除生成文件", "Delete generated file")}
        description={t(
          "删除后无法再次下载此文件，任务记录仍会保留。",
          "The file will no longer be downloadable. Task history is retained.",
        )}
        confirmLabel={t("删除", "Delete")}
        onConfirm={remove}
        loading={busy}
        destructive
        cancelLabel={t("取消", "Cancel")}
      />
    </section>
  );
}
