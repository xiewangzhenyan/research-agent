"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useLocale } from "next-intl";
import { currentProject, projectFetch } from "@/lib/project-scope";
import { useAuthStore, useConversationStore } from "@/stores";

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename.replace(/[\\/\u0000-\u001f]/g, "_");
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Ignore late downloads after switching account, project or conversation. */
export function useFileDownload(context: string) {
  const zh = useLocale() === "zh";
  const userId = useAuthStore((s) => s.user?.id);
  const projectId = currentProject()?.id;
  const [busy, setBusy] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    setBusy(null);
    return () => {
      controller.current?.abort();
      controller.current = null;
    };
  }, [userId, projectId, context]);
  async function download(url: string, name: string, init?: RequestInit) {
    if (controller.current || !userId) return;
    const abort = new AbortController();
    controller.current = abort;
    const selection = useConversationStore.getState().selectionVersion;
    const current = () =>
      !abort.signal.aborted &&
      useAuthStore.getState().user?.id === userId &&
      currentProject()?.id === projectId &&
      useConversationStore.getState().selectionVersion === selection;
    setBusy(name);
    try {
      const response = await projectFetch(url, {
        ...init,
        signal: abort.signal,
        cache: "no-store",
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : zh
              ? "下载失败，文件可能已删除，请重试。"
              : "Download failed. The file may have been removed.",
        );
      }
      const blob = await response.blob();
      if (current()) saveBlob(blob, name);
    } catch (error) {
      if (current())
        toast.error(
          error instanceof Error ? error.message : zh ? "下载失败，请重试。" : "Download failed.",
        );
    } finally {
      if (controller.current === abort) {
        controller.current = null;
        setBusy(null);
      }
    }
  }
  return { download, busy };
}
