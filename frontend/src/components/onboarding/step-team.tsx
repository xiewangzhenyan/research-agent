"use client";
import Link from "next/link";
import { useLocale } from "next-intl";

import { OnboardingShell } from "./onboarding-shell";
export function StepTeam() {
  const locale = useLocale();
  const zh = locale === "zh";
  const prefix = zh ? "" : `/${locale}`;

  return (
    <OnboardingShell
      step="team"
      title={zh ? "团队功能状态" : "Team availability"}
      description={
        zh
          ? "团队邀请和组织管理暂未开放。"
          : "Team invitations and organization management are not enabled."
      }
    >
      <p className="rounded-xl border p-6 leading-relaxed">
        {zh
          ? "当前可使用个人账号保存和管理对话。这里不会发送邀请邮件。"
          : "Use your own account to save and manage conversations. No invitation emails are sent here."}
      </p>
      <div className="mt-8 flex gap-4">
        <Link
          className="bg-foreground text-background rounded-full px-6 py-3"
          href={`${prefix}/onboarding/done`}
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
