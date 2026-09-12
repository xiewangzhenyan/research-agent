"use client";
import Link from "next/link";
import { useLocale } from "next-intl";
import { useEffect } from "react";
import { markOnboardingCompleted } from "./onboarding-state";
import { OnboardingShell } from "./onboarding-shell";
export function StepDone() {
  const locale = useLocale();
  const zh = locale === "zh";
  const prefix = zh ? "" : `/${locale}`;
  useEffect(() => {
    void markOnboardingCompleted();
  }, []);
  return (
    <OnboardingShell
      step="done"
      title={zh ? "可以开始聊天了" : "Ready to chat"}
      description={zh ? "发送你的第一个问题。" : "Send your first question."}
    >
      <p className="rounded-xl border p-6 leading-relaxed">
        {zh
          ? "也可以添加聊天附件，并根据需要选择模型。"
          : "You can also attach a file and choose a model in chat."}
      </p>
      <div className="mt-8 flex gap-4">
        <Link
          className="bg-foreground text-background rounded-full px-6 py-3"
          href={`${prefix}/chat`}
        >
          {zh ? "打开聊天" : "Open chat"}
        </Link>
        <Link className="rounded-full border px-6 py-3" href={`${prefix}/help`}>
          {zh ? "使用帮助" : "Help"}
        </Link>
      </div>
    </OnboardingShell>
  );
}
