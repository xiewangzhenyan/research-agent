"use client";
import { useState } from "react";
import { Paperclip, X, Loader2 } from "lucide-react";
export type InputFile = { id: string; filename: string; size: number };

export function InputFiles({
  files,
  onChange,
  onBusy,
  enabled,
  zh = true,
}: {
  files: InputFile[];
  onChange: (files: InputFile[]) => void;
  onBusy: (busy: boolean) => void;
  enabled: boolean;
  zh?: boolean;
}) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const t = (cn: string, en: string) => (zh ? cn : en);
  async function upload(selected: FileList | null) {
    if (!selected || !enabled) return;
    const pending = Array.from(selected);
    if (
      files.length + pending.length > 5 ||
      [...files, ...pending].reduce((sum, f) => sum + f.size, 0) > 5 * 1024 ** 2
    ) {
      setError(t("最多 5 个文件，总大小不超过 5 MiB", "Up to 5 files, 5 MiB total"));
      return;
    }
    if (pending.some((f) => !/\.(csv|json|txt|md|png|jpe?g)$/i.test(f.name))) {
      setError(t("支持 CSV、JSON、文本、PNG 和 JPEG", "CSV, JSON, text, PNG and JPEG supported"));
      return;
    }
    setUploading(true);
    onBusy(true);
    setError("");
    const next = [...files];
    try {
      for (const file of pending) {
        const form = new FormData();
        form.append("file", file);
        const response = await fetch("/api/files/upload", { method: "POST", body: form });
        const data = await response.json();
        if (!response.ok)
          throw new Error(
            typeof data.detail === "string"
              ? data.detail
              : data.error?.message || t("文件上传失败", "Upload failed"),
          );
        next.push({ id: data.id, filename: data.filename, size: data.size });
        onChange([...next]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("文件上传失败", "Upload failed"));
    } finally {
      setUploading(false);
      onBusy(false);
    }
  }
  return (
    <div className="border-border rounded-xl border border-dashed p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium">{t("计算输入文件", "Calculation inputs")}</span>
        <span className="text-muted-foreground text-xs">
          {files.length}/5 · {(files.reduce((s, f) => s + f.size, 0) / 1024 ** 2).toFixed(1)}/5 MiB
        </span>
      </div>
      <p className="text-muted-foreground mt-2 text-xs leading-5">
        {enabled
          ? t(
              "文件以只读方式提供给计算任务，支持 CSV、JSON、文本和图片。",
              "Read-only CSV, JSON, text and image inputs.",
            )
          : t(
              "独立文件沙箱就绪并勾选 Python 后可上传计算文件。",
              "Enable Python after the file sandbox is ready to attach inputs.",
            )}
      </p>
      <label
        className={`mt-3 inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs ${!enabled || uploading ? "cursor-not-allowed opacity-50" : "hover:bg-muted cursor-pointer"}`}
      >
        {uploading ? (
          <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
        ) : (
          <Paperclip className="h-4 w-4" />
        )}
        {uploading ? t("正在上传", "Uploading") : t("添加文件", "Add files")}
        <input
          aria-label={t("添加计算文件", "Add calculation files")}
          className="sr-only"
          type="file"
          multiple
          accept=".csv,.json,.txt,.md,.png,.jpg,.jpeg"
          disabled={!enabled || uploading}
          onChange={(e) => {
            void upload(e.target.files);
            e.target.value = "";
          }}
        />
      </label>
      {files.length > 0 && (
        <ul className="mt-3 space-y-2">
          {files.map((f) => (
            <li
              key={f.id}
              className="bg-muted/40 flex min-w-0 items-center gap-2 rounded-lg px-3 py-2 text-xs"
            >
              <span className="min-w-0 flex-1 truncate">{f.filename}</span>
              <span className="text-muted-foreground">{Math.ceil(f.size / 1024)} KiB</span>
              <button
                type="button"
                disabled={uploading}
                aria-label={t("移除", "Remove") + " " + f.filename}
                onClick={() => onChange(files.filter((v) => v.id !== f.id))}
              >
                <X className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p role="alert" className="text-destructive mt-2 text-xs">
          {error}
        </p>
      )}
    </div>
  );
}
