"use client";

import Link from "next/link";
import { Download, FileSearch, MoreHorizontal, Pencil, RotateCcw, Trash2 } from "lucide-react";
import {
  Button,
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui";
import type { KnowledgeDocument } from "@/lib/knowledge";

export function DocumentActions({
  document: doc,
  baseId,
  busy,
  onEdit,
  onPreview,
  onRetry,
  onRemove,
}: {
  document: KnowledgeDocument;
  baseId: string;
  busy: boolean;
  onEdit: () => void;
  onPreview: () => void;
  onRetry: () => void;
  onRemove: () => void;
}) {
  // Open dialogs after the menu restores focus, so it cannot steal their focus.
  const afterClose = (callback: () => void) => requestAnimationFrame(callback);
  return (
    <div className="console-doc-actions flex flex-wrap items-center gap-1 text-xs">
      {doc.status === "ready" && (
        <Button asChild variant="ghost" size="sm" className="text-brand">
          <Link href={`/chat?knowledge=${baseId}&document=${doc.id}`}>围绕此资料提问</Link>
        </Button>
      )}
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-9 w-9"
            aria-label={`资料操作：${doc.title || doc.filename}`}
          >
            <MoreHorizontal size={18} />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" collisionPadding={12}>
          {(doc.source_kind === "manual" || doc.source_kind === "faq") && (
            <DropdownMenuItem disabled={busy} onSelect={() => afterClose(onEdit)}>
              <Pencil size={15} className="mr-2" />
              编辑内容
            </DropdownMenuItem>
          )}
          <DropdownMenuItem asChild>
            <a href={`/api/knowledge/documents/${doc.id}/download`}>
              <Download size={15} className="mr-2" />
              下载原文
            </a>
          </DropdownMenuItem>
          {doc.status === "ready" && (
            <DropdownMenuItem onSelect={() => afterClose(onPreview)}>
              <FileSearch size={15} className="mr-2" />
              查看分块
            </DropdownMenuItem>
          )}
          {(doc.status === "failed" || doc.status === "ready") && (
            <DropdownMenuItem disabled={busy} onSelect={onRetry}>
              <RotateCcw size={15} className="mr-2" />
              重新处理
            </DropdownMenuItem>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            disabled={busy}
            className="text-destructive focus:text-destructive"
            onSelect={() => afterClose(onRemove)}
          >
            <Trash2 size={15} className="mr-2" />
            删除资料
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
