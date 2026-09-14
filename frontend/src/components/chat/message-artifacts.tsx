"use client";
import { FileText, Download, Loader2 } from "lucide-react";
import { useLocale } from "next-intl";
import { extractArtifacts } from "@/lib/chat-artifacts";
import { useFileDownload } from "@/hooks/use-file-download";
import type { ChatMessage } from "@/types";

export function MessageArtifacts({ message }: { message: ChatMessage }) {
  const zh = useLocale() === "zh";
  const { download, busy } = useFileDownload(message.id);
  const files = extractArtifacts(message);
  if (!files.length) return null;
  return (
    <ul
      aria-label={zh ? "生成文件" : "Generated files"}
      className="grid w-full gap-2 sm:grid-cols-2"
    >
      {files.map((file) => (
        <li key={file.id} className="min-w-0">
          <button
            type="button"
            disabled={!!busy}
            aria-label={`${zh ? "下载" : "Download"} ${file.name}`}
            onClick={() => download(`/api/tasks/${file.run_id}/artifacts/${file.id}`, file.name)}
            className="border-border hover:bg-muted/50 flex min-h-18 w-full items-center gap-3 rounded-2xl border px-4 py-3 text-left disabled:opacity-60"
          >
            <FileText className="text-muted-foreground h-6 w-6 shrink-0" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{file.name}</span>
              <span className="text-muted-foreground text-xs">
                {Math.max(1, Math.ceil(file.size / 1024))} KB · {zh ? "已保存" : "Saved"}
              </span>
            </span>
            {busy === file.name ? (
              <Loader2 className="h-4 w-4 shrink-0 animate-spin motion-reduce:animate-none" />
            ) : (
              <Download className="text-muted-foreground h-4 w-4 shrink-0" />
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}
