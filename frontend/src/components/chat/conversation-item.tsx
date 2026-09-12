"use client";

import { useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  Archive,
  ArchiveRestore,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Share2,
  Trash2,
} from "lucide-react";
import {
  Button,
  Input,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui";
import { cn } from "@/lib/utils";
import type { Conversation } from "@/types";

type MutationResult = boolean | void | Promise<boolean | void>;
export interface ConversationItemProps {
  conversation: Conversation;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => MutationResult;
  onArchive: () => void;
  onUnarchive: () => void;
  onRename: (title: string) => MutationResult;
  onShare: () => void;
}

export function ConversationItem({
  conversation,
  isActive,
  onSelect,
  onDelete,
  onArchive,
  onUnarchive,
  onRename,
  onShare,
}: ConversationItemProps) {
  const t = useTranslations("chat");
  const zh = useLocale() === "zh";
  const [dialog, setDialog] = useState<"rename" | "delete" | null>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const trigger = useRef<HTMLButtonElement>(null);
  const displayTitle = conversation.title || t("newConversation");
  const open = (kind: "rename" | "delete") => {
    setTitle(conversation.title || "");
    setError("");
    setDialog(kind);
  };
  const save = async () => {
    if (busy || (dialog === "rename" && !title.trim())) return;
    setBusy(true);
    setError("");
    try {
      const success = await (dialog === "rename" ? onRename(title.trim()) : onDelete());
      if (success === false) throw new Error("Mutation failed");
      setDialog(null);
    } catch {
      setError(
        zh
          ? "操作未完成，请重试。你的修改仍保留在这里。"
          : "The action failed. Your changes are retained; please retry.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <div
      className={cn(
        "conversation-row group relative flex min-h-11 items-center gap-1 rounded-lg border px-1 transition-colors",
        isActive ? "border-brand/15 bg-accent" : "hover:bg-muted border-transparent",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-current={isActive ? "page" : undefined}
        title={displayTitle}
        className="flex min-h-11 min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-2 text-left"
      >
        <MessageSquare
          size={15}
          className={cn("shrink-0", isActive ? "text-brand" : "text-muted-foreground")}
        />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px]">{displayTitle}</span>
          <span className="text-muted-foreground mt-1 block text-[10px]">
            {new Date(conversation.updated_at || conversation.created_at).toLocaleDateString(
              zh ? "zh-CN" : "en-US",
              { month: "short", day: "numeric" },
            )}
          </span>
        </span>
      </button>
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <Button
            ref={trigger}
            type="button"
            variant="ghost"
            size="icon"
            aria-label={zh ? `会话操作：${displayTitle}` : `Conversation actions: ${displayTitle}`}
            className="text-muted-foreground h-9 w-9 shrink-0"
          >
            <MoreHorizontal size={17} />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="start"
          side="right"
          sideOffset={8}
          collisionPadding={12}
          onCloseAutoFocus={(e) => {
            if (dialog) e.preventDefault();
          }}
        >
          <DropdownMenuItem onSelect={() => open("rename")}>
            <Pencil size={15} className="mr-2" />
            {t("rename")}
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={onShare}>
            <Share2 size={15} className="mr-2" />
            {t("share")}
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={conversation.is_archived ? onUnarchive : onArchive}>
            {conversation.is_archived ? (
              <ArchiveRestore size={15} className="mr-2" />
            ) : (
              <Archive size={15} className="mr-2" />
            )}
            {conversation.is_archived ? t("restore") : t("archive")}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            className="text-destructive focus:text-destructive"
            onSelect={() => open("delete")}
          >
            <Trash2 size={15} className="mr-2" />
            {t("delete")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog
        open={dialog !== null}
        onOpenChange={(value) => {
          if (!value && !busy) setDialog(null);
        }}
      >
        <DialogContent
          className="sm:max-w-md"
          onCloseAutoFocus={(e) => {
            e.preventDefault();
            trigger.current?.focus();
          }}
        >
          <DialogHeader>
            <DialogTitle>
              {dialog === "rename"
                ? zh
                  ? "重命名会话"
                  : "Rename conversation"
                : zh
                  ? "删除会话？"
                  : "Delete conversation?"}
            </DialogTitle>
            <DialogDescription className="break-words">
              {dialog === "rename"
                ? zh
                  ? "为这段对话设置一个容易查找的名称。"
                  : "Give this conversation a recognizable name."
                : zh
                  ? `将永久删除「${displayTitle}」及其中的消息，无法恢复。`
                  : `Permanently delete “${displayTitle}” and its messages. This cannot be undone.`}
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
            className="space-y-4"
          >
            {dialog === "rename" && (
              <label className="block space-y-2 text-sm">
                <span>{zh ? "会话名称" : "Conversation name"}</span>
                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  maxLength={200}
                  required
                  disabled={busy}
                />
              </label>
            )}
            {error && (
              <p role="alert" className="text-destructive text-sm">
                {error}
              </p>
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => setDialog(null)}
              >
                {zh ? "取消" : "Cancel"}
              </Button>
              <Button
                type="submit"
                variant={dialog === "delete" ? "destructive" : "default"}
                disabled={busy || (dialog === "rename" && !title.trim())}
              >
                {busy
                  ? zh
                    ? "正在处理…"
                    : "Saving…"
                  : dialog === "delete"
                    ? zh
                      ? "确认删除"
                      : "Delete"
                    : zh
                      ? "保存名称"
                      : "Save name"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
