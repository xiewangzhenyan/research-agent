"use client";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchTools } from "@/lib/tool-catalog";
import { useAuthStore } from "@/stores";
import { useKnowledgeStore } from "@/stores/knowledge-store";

export function ChatToolOptions({ onChange }: { onChange: (value: boolean) => void }) {
  const userId = useAuthStore((s) => s.user?.id);
  const strict = useKnowledgeStore((s) => s.strict && s.ids.length > 0);
  const [open, setOpen] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const catalog = useQuery({
    queryKey: ["tools", userId],
    queryFn: ({ signal }) => fetchTools(signal),
    enabled: open && !!userId,
    staleTime: 30000,
  });
  const python = catalog.data?.items.find((t) => t.id === "run_python");
  useEffect(() => {
    if (strict) setEnabled(false);
  }, [strict]);
  useEffect(() => {
    onChange(enabled && !strict);
  }, [enabled, strict, onChange]);
  return (
    <details className="px-3 py-2 text-xs sm:px-4" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="text-muted-foreground cursor-pointer">
        工具权限{enabled && !strict ? " · 已允许 Python 计算" : ""}
      </summary>
      <div className="space-y-2 pt-3 pb-1">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={enabled && !strict}
            disabled={!python?.available || strict}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          允许本会话使用隔离 Python 计算
        </label>
        <p className="text-muted-foreground leading-5">
          {strict
            ? "严格资料模式只使用原文证据，关闭后可启用计算。"
            : "由助手按问题需要调用。附件作为只读计算输入，最多 5 个、合计 5 MiB；生成文件可在对应回答的执行详情中下载。"}
        </p>
        {catalog.isPending && <p>正在检查工具…</p>}
        {python && !python.available && <p>{python.reason ?? "计算工具暂不可用"}</p>}
        {catalog.isError && (
          <button type="button" className="underline" onClick={() => catalog.refetch()}>
            工具读取失败，点击重试
          </button>
        )}
      </div>
    </details>
  );
}
