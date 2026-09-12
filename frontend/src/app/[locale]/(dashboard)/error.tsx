"use client";

import { useEffect } from "react";
import { useLocale } from "next-intl";

import { ErrorState } from "@/components/states";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const zh = useLocale() === "zh";
  useEffect(() => {
    console.error("Dashboard error:", error);
  }, [error]);

  return (
    <div className="flex min-h-0 flex-1 items-center justify-center py-10">
      <ErrorState
        className="w-full max-w-md"
        title={zh ? "页面暂时无法加载" : "This section failed to load"}
        description={
          zh
            ? "加载时出现问题，请点击重试。"
            : error.digest
              ? `An unexpected error occurred. Error ID: ${error.digest}`
              : "An unexpected error occurred while loading this view. Please try again."
        }
        cta={{ label: zh ? "重试" : "Try again", onClick: () => reset() }}
      />
    </div>
  );
}
