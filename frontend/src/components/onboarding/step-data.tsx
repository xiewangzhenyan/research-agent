"use client";
import Link from "next/link";
import { useLocale } from "next-intl";

import { OnboardingShell } from "./onboarding-shell";
export function StepData() {
  const locale = useLocale();
  const zh = locale === "zh";
  const prefix = zh ? "" : `/${locale}`;

  return (
    <OnboardingShell
      step="data"
      title={zh ? "使用聊天附件" : "Use chat attachments"}
      description={
        zh
          ? "在聊天输入框添加文件，再发送关于文件的问题。"
          : "Attach a file in the chat input, then send a question about it."
      }
    >
      <p className="rounded-xl border p-6 leading-relaxed">
        {zh
          ? "知识库索引和云盘同步暂未开放。本引导不会上传文件，也不会把文件加入知识库。"
          : "Knowledge indexing and cloud storage sync are not available. This guide does not upload or index files."}
      </p>
      <div className="mt-8 flex gap-4">
        <Link
          className="bg-foreground text-background rounded-full px-6 py-3"
          href={`${prefix}/onboarding/team`}
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
