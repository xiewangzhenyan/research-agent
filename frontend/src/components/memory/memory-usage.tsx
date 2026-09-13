"use client";
import Link from "next/link";
import { useLocale } from "next-intl";
import { Brain } from "lucide-react";
import type { MemoryUsage } from "@/lib/memory";

export function MemoryUsageBadge({ usage }: { usage?: MemoryUsage }) {
  const zh = useLocale() === "zh";
  if (!usage?.items.length) return null;
  const used = usage.items.map((item) => `${item.id}:${item.revision}`).join(",");
  return (
    <Link
      href={`/memory?used=${encodeURIComponent(used)}`}
      className="text-muted-foreground hover:text-brand inline-flex min-h-8 items-center gap-1.5 text-xs"
    >
      <Brain size={13} />
      {zh
        ? `本次使用 ${usage.items.length} 条项目记忆`
        : `Used ${usage.items.length} project memories`}
      {usage.omitted > 0 && (zh ? " · 其余未载入" : " · Others not loaded")}
    </Link>
  );
}
