"use client";
import Link from "next/link";
import { useLocale } from "next-intl";

import { OnboardingShell } from "./onboarding-shell";
export function StepAgent() {
  const locale = useLocale();
  const zh = locale === "zh";
  const prefix = zh ? "" : `/${locale}`;

  return (
    <OnboardingShell
      step="agent"
      title={zh ? "选择聊天模型" : "Choose a chat model"}
      description={
        zh
          ? "在聊天输入框的模型菜单中选择已配置的模型。"
          : "Select an available model from the chat controls."
      }
    >
      <p className="rounded-xl border p-6 leading-relaxed">
        {zh
          ? "默认模型由管理员统一设置；新对话可直接使用默认配置。"
          : "The administrator configures the default model. You can start a new chat with the default settings."}
      </p>
      <div className="mt-8 flex gap-4">
        <Link
          className="bg-foreground text-background rounded-full px-6 py-3"
          href={`${prefix}/onboarding/data`}
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
