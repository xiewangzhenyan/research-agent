"use client";

import { useLocale } from "next-intl";
import { SlashCommandsManager } from "@/components/settings/slash-commands-manager";

export default function SlashCommandsSettingsPage() {
  const isZh = useLocale() === "zh";
  return (
    <div className="space-y-6">
      <section className="border-border bg-card rounded-xl border">
        <header className="border-border border-b px-5 py-4">
          <h2 className="text-foreground text-sm font-semibold">{isZh ? "斜杠命令" : "Slash commands"}</h2>
          <p className="text-muted-foreground mt-1 text-xs">
            {isZh
              ? "自定义聊天中的 /命令面板：可以停用内置命令，也可以创建自己的快捷提示词。"
              : "Customize the /command palette in chat — disable built-ins, or define your own quick prompts."}
          </p>
        </header>
        <div className="px-5 py-5">
          <SlashCommandsManager />
        </div>
      </section>
    </div>
  );
}
