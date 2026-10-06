"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale } from "next-intl";

import { Button } from "@/components/ui/button";
import { ROUTES } from "@/lib/constants";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const router = useRouter();
  const zh = useLocale() === "zh";

  useEffect(() => {
    console.error("Page error:", error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-4 text-center">
      <p className="text-destructive font-mono text-xs font-semibold tracking-widest uppercase">
        Error
      </p>
      <h1 className="text-foreground mt-2 text-2xl font-bold tracking-tight sm:text-3xl">
        {zh ? "页面出错了" : "Something went wrong"}
      </h1>
      <p className="text-muted-foreground mt-3 max-w-md">
        {zh ? "加载这个页面时出现问题，请重试。" : "An error occurred while loading this page. Please try again."}
      </p>
      {error.digest && (
        <p className="text-muted-foreground/60 mt-1 font-mono text-xs">
          {zh ? "错误编号：" : "Error ID: "}
          {error.digest}
        </p>
      )}
      <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
        <Button onClick={reset}>{zh ? "重试" : "Try again"}</Button>
        <Button variant="secondary" onClick={() => router.back()}>
          {zh ? "返回上一页" : "Go back"}
        </Button>
        <Button variant="outline" asChild>
          <Link href={ROUTES.HOME}>{zh ? "回到首页" : "Go home"}</Link>
        </Button>
      </div>
    </div>
  );
}
