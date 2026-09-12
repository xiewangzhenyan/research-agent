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
      className="bg-card fixed bottom-4 left-4 z-50 max-w-sm rounded-2xl border p-5 shadow-xl"
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
        className="mt-3 rounded-full border px-4 py-2 text-sm"
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
