"use client";
import { useState } from "react";
import { useLocale } from "next-intl";
import { useQueryClient } from "@tanstack/react-query";
import { Brain } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { currentProject } from "@/lib/project-scope";
import { useAuthStore } from "@/stores";
import { kindLabel, memoryError, memoryKey, type MemoryItem, type MemoryKind } from "@/lib/memory";
import { useUnsavedInput } from "@/hooks/use-unsaved-input";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Textarea,
} from "@/components/ui";
import type { ChatMessage } from "@/types";

export function MemoryEditor({
  item,
  message,
  onClose,
}: {
  item?: MemoryItem;
  message?: ChatMessage;
  onClose: () => void;
}) {
  const zh = useLocale() === "zh";
  const t = (cn: string, en: string) => (zh ? cn : en);
  const client = useQueryClient();
  const project = currentProject();
  const userId = useAuthStore((s) => s.user?.id);
  const [title, setTitle] = useState(
    item?.title ??
      message?.content
        .split("\n")[0]
        ?.replace(/^#+\s*/, "")
        .slice(0, 80) ??
      "",
  );
  const [content, setContent] = useState(item?.content ?? message?.content ?? "");
  const [kind, setKind] = useState<MemoryKind>(item?.kind ?? "note");
  const [pinned, setPinned] = useState(item?.pinned ?? false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const initialTitle =
    item?.title ??
    message?.content
      .split("\n")[0]
      ?.replace(/^#+\s*/, "")
      .slice(0, 80) ??
    "";
  useUnsavedInput(
    busy ||
      content !== (item?.content ?? message?.content ?? "") ||
      title !== initialTitle ||
      kind !== (item?.kind ?? "note") ||
      pinned !== (item?.pinned ?? false),
  );
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const key = memoryKey();
    try {
      const body = {
        title: title.trim(),
        content: content.trim(),
        kind,
        pinned,
        source_message_id: item?.source_message_id ?? message?.id ?? null,
      };
      if (item) await apiClient.put(`/memory/${item.id}`, { ...body, revision: item.revision });
      else await apiClient.post("/memory", body);
      if (useAuthStore.getState().user?.id !== userId || currentProject()?.id !== project?.id)
        return;
      await client.invalidateQueries({ queryKey: key });
      onClose();
    } catch (e) {
      setError(memoryError(e, zh));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent className="flex max-h-[90dvh] w-[calc(100%-1.5rem)] flex-col gap-0 overflow-hidden rounded-2xl p-0 sm:max-w-xl">
        <DialogHeader className="shrink-0 border-b px-6 py-5">
          <DialogTitle>
            {item ? t("编辑记忆", "Edit memory") : t("保存到项目记忆", "Save project memory")}
          </DialogTitle>
          <DialogDescription>
            {t("仅保存在", "Saved only in")} {project?.name ?? t("默认项目", "Default project")}。
            {t("请确认内容准确，再保存。", "Review the content before saving.")}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={save} className="flex min-h-0 flex-col">
          <div className="space-y-5 overflow-y-auto px-6 py-5">
            <div className="space-y-2">
              <Label htmlFor="memory-title">{t("标题", "Title")}</Label>
              <Input
                id="memory-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={80}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="memory-kind">{t("类型", "Type")}</Label>
              <select
                id="memory-kind"
                value={kind}
                onChange={(e) => setKind(e.target.value as MemoryKind)}
                className="bg-background h-10 w-full rounded-md border px-3 text-sm"
              >
                {(["note", "preference", "decision", "constraint"] as MemoryKind[]).map((k) => (
                  <option key={k} value={k}>
                    {kindLabel(k, zh)}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="memory-content">{t("需要记住的内容", "What to remember")}</Label>
              <Textarea
                id="memory-content"
                rows={7}
                value={content}
                onChange={(e) => setContent(e.target.value)}
                required
                aria-describedby="memory-length"
              />
              <p
                id="memory-length"
                className={
                  content.length > 1200
                    ? "text-destructive text-xs"
                    : "text-muted-foreground text-xs"
                }
              >
                {content.length}/1200 ·{" "}
                {t(
                  "请保留必要背景、数值和限制条件。",
                  "Keep necessary context, numbers and constraints.",
                )}
              </p>
            </div>
            <label
              htmlFor="memory-pinned"
              aria-label={t("优先回忆", "Prioritize recall")}
              className="flex items-start gap-3 rounded-xl border p-3 text-sm"
            >
              <input
                id="memory-pinned"
                type="checkbox"
                checked={pinned}
                onChange={(e) => setPinned(e.target.checked)}
                className="mt-1 accent-emerald-500"
              />
              <span>
                {t("优先回忆", "Prioritize recall")}
                <span className="text-muted-foreground mt-1 block text-xs">
                  {t(
                    "适合通用偏好或长期约束；开启记忆后，在预算允许时优先用于新回答。",
                    "For preferences and lasting constraints, included first when memory is enabled and space permits.",
                  )}
                </span>
              </span>
            </label>
            {(message || item?.source_message_id) && (
              <p className="text-muted-foreground text-xs">
                {t(
                  "这条记忆由消息整理，保存后仍可编辑。删除来源会话时，关联记忆也会删除。",
                  "Adapted from a message. Deleting the source conversation also deletes this memory.",
                )}
              </p>
            )}
            <p className="text-muted-foreground text-xs">
              {t(
                "保存不会自动开启记忆。可在项目记忆页开启聊天回忆。",
                "Saving does not enable recall. Enable it on the project memory page.",
              )}
            </p>
            {error && (
              <p role="alert" className="text-destructive text-sm">
                {error}
              </p>
            )}
          </div>
          <div className="flex shrink-0 justify-end gap-3 border-t px-6 py-4">
            <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
              {t("取消", "Cancel")}
            </Button>
            <Button
              type="submit"
              disabled={busy || !title.trim() || !content.trim() || content.length > 1200}
            >
              {busy ? t("正在保存…", "Saving…") : t("确认保存", "Confirm and save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function RememberMessage({ message }: { message: ChatMessage }) {
  const [open, setOpen] = useState(false);
  const zh = useLocale() === "zh";
  if (message.isTemporaryId || !/^[0-9a-f-]{36}$/i.test(message.id)) return null;
  return (
    <>
      <button
        type="button"
        className="bg-muted hover:bg-muted/80 text-muted-foreground inline-flex h-6 w-6 items-center justify-center rounded-md"
        aria-label={zh ? "记住这条消息" : "Remember this message"}
        title={zh ? "记住这条消息" : "Remember this message"}
        onClick={() => setOpen(true)}
      >
        <Brain className="h-3.5 w-3.5" />
      </button>
      {open && <MemoryEditor message={message} onClose={() => setOpen(false)} />}
    </>
  );
}
