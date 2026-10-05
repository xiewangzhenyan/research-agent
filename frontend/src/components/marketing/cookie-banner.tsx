"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useLocale } from "next-intl";
import { ROUTES } from "@/lib/constants";
export function CookieBanner() {
  const zh = useLocale() === "zh";
  const [show, setShow] = useState(false);
  useEffect(() => {
    try {
      setShow(!localStorage.getItem("cookie.notice.read"));
    } catch {
      setShow(true);
    }
  }, []);
  if (!show) return null;
  return (
    <aside
      aria-label={zh ? "Cookie 说明" : "Cookie notice"}
      className="bg-popover text-popover-foreground animate-in fade-in-0 slide-in-from-bottom-2 fixed bottom-4 left-4 z-50 max-w-sm rounded-2xl border p-5 shadow-[var(--shadow-overlay)]"
    >
      <p className="text-sm leading-relaxed">
        {zh
          ? "本站使用 Cookie 保存登录状态和语言偏好。"
          : "This site uses cookies for sign-in and language preferences."}{" "}
        <Link className="underline" href={ROUTES.LEGAL_COOKIES}>
          {zh ? "查看说明" : "Learn more"}
        </Link>
      </p>
      <button
        className="bg-brand text-brand-foreground hover:bg-brand-hover mt-3 rounded-full px-4 py-2 text-sm font-medium transition-colors"
        onClick={() => {
          try {
            localStorage.setItem("cookie.notice.read", "1");
          } catch {}
          setShow(false);
        }}
      >
        {zh ? "知道了" : "Got it"}
      </button>
    </aside>
  );
}
