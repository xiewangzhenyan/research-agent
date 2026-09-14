"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, Plus, Paperclip, ChartNoAxesCombined } from "lucide-react";
import { useLocale } from "next-intl";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui";
import { fetchTools } from "@/lib/tool-catalog";
import { useAuthStore } from "@/stores";
import { useKnowledgeStore } from "@/stores/knowledge-store";

export function ChatToolsMenu({
  onAttach,
  onPythonChange,
  disabled,
}: {
  onAttach: () => void;
  onPythonChange?: (enabled: boolean) => void;
  disabled?: boolean;
}) {
  const zh = useLocale() === "zh";
  const userId = useAuthStore((s) => s.user?.id);
  const strict = useKnowledgeStore((s) => s.strict && s.ids.length > 0);
  const [open, setOpen] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const catalog = useQuery({
    queryKey: ["tools", userId],
    queryFn: ({ signal }) => fetchTools(signal),
    enabled: open && !!userId && !!onPythonChange,
    staleTime: 60_000,
  });
  const python = catalog.data?.items.find((t) => t.id === "run_python");
  useEffect(() => {
    if (strict) setEnabled(false);
  }, [strict]);
  useEffect(() => {
    onPythonChange?.(enabled && !strict);
  }, [enabled, strict, onPythonChange]);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="composer-icon relative"
          disabled={disabled}
          aria-label={zh ? "添加文件与工具" : "Files and tools"}
        >
          <Plus className="h-5 w-5" />
          {enabled && !strict && (
            <span className="bg-foreground absolute right-1 bottom-1 h-1.5 w-1.5 rounded-full" />
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" side="top" className="w-64 rounded-2xl p-1.5">
        <button
          type="button"
          className="composer-menu-item"
          onClick={() => {
            setOpen(false);
            onAttach();
          }}
        >
          <Paperclip className="h-4 w-4" />
          {zh ? "上传文件" : "Upload files"}
        </button>
        {onPythonChange && (
          <>
            <button
              type="button"
              className="composer-menu-item"
              role="switch"
              aria-checked={enabled && !strict}
              disabled={strict || !python?.available}
              onClick={() => {
                setEnabled(!enabled);
                setOpen(false);
              }}
            >
              <ChartNoAxesCombined className="h-4 w-4" />
              <span className="flex-1 text-left">{zh ? "数据分析" : "Data analysis"}</span>
              {enabled && !strict && <Check className="h-4 w-4" />}
            </button>
            <p className="text-muted-foreground px-3 py-2 text-xs leading-5">
              {strict
                ? zh
                  ? "当前仅使用知识库原文回答。"
                  : "Answers currently use knowledge sources only."
                : catalog.isError
                  ? zh
                    ? "数据分析状态暂时无法读取。"
                    : "Data analysis status is unavailable."
                  : catalog.isPending
                    ? zh
                      ? "正在检查数据分析服务…"
                      : "Checking data analysis…"
                    : !python?.available
                      ? zh
                        ? "数据分析暂不可用。"
                        : "Data analysis is unavailable."
                      : zh
                        ? "分析附件、运行计算并生成文件。"
                        : "Analyze attachments, run calculations and create files."}
            </p>
          </>
        )}
      </PopoverContent>
    </Popover>
  );
}
