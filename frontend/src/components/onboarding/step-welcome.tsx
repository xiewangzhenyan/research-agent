"use client";
import Link from "next/link";
import { useLocale } from "next-intl";

import { OnboardingShell } from "./onboarding-shell";
export function StepWelcome() {
  const locale = useLocale();
  const zh = locale === "zh";
  const prefix = zh ? "" : `/${locale}`;

  return (
    <OnboardingShell
      step="welcome"
      title={zh ? "开始使用" : "Get started"}
      description={
        zh
          ? "了解当前开放的聊天、附件和账户功能。"
          : "Learn about chat, attachments, and account features."
      }
    >
      <p className="rounded-xl border p-6 leading-relaxed">
        {zh
          ? "你可以直接开始对话，也可以继续查看简短使用说明。"
          : "Start chatting now, or continue through this short guide."}
      </p>
      <div className="mt-8 flex gap-4">
        <Link
          className="bg-foreground text-background rounded-full px-6 py-3"
          href={`${prefix}/onboarding/agent`}
        >
          {zh ? "继续" : "Continue"}
        </Link>
        <Link className="rounded-full border px-6 py-3" href={`${prefix}/help`}>
          {zh ? "使用帮助" : "Help"}
        </Link>
      </div>
    </OnboardingShell>
  );
}
