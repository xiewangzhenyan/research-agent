"use client";

import { BookOpenText, FileSearch, GitCompareArrows, ScrollText } from "lucide-react";
import { useTranslations } from "next-intl";

import { ResearchMark } from "@/components/brand/research-mark";
import { useAuth } from "@/hooks";

import { RoleStrip } from "./role-strip";

/** Research-shaped starters. "compare" and "review" use the wording that lets the
 *  backend route a question to the four-role workflow when a knowledge base is
 *  connected in strict mode; nothing here forces that route. */
const PROMPTS = [
  { key: "summary", icon: FileSearch, role: "write" },
  { key: "compare", icon: GitCompareArrows, role: "research" },
  { key: "explain", icon: BookOpenText, role: "plan" },
  { key: "review", icon: ScrollText, role: "review" },
] as const;

interface ChatEmptyStateProps {
  onPick: (prompt: string) => void;
}

export function ChatEmptyState({ onPick }: ChatEmptyStateProps) {
  const { user } = useAuth();
  const t = useTranslations("chat.empty");
  const firstName = user?.full_name?.split(" ")[0] || user?.email?.split("@")[0];

  return (
    <div className="chat-welcome mx-auto w-full max-w-2xl px-4 py-6 md:py-10">
      <div className="stagger flex flex-col items-center text-center">
        <span className="relative mb-5 inline-grid place-items-center">
          <span
            aria-hidden
            className="bg-brand/25 absolute inset-0 rounded-[20px] blur-xl motion-safe:animate-[breathe_3.6s_ease-in-out_infinite]"
          />
          <ResearchMark size={52} animated className="relative" />
        </span>
        <h2 className="text-foreground font-display text-2xl font-semibold tracking-tight md:text-3xl">
          {firstName ? t("greetingNamed", { name: firstName }) : t("greeting")}
        </h2>
        <p className="text-muted-foreground mx-auto mt-2 max-w-md text-sm leading-relaxed">
          {t("subtitle")}
        </p>
        <RoleStrip label={t("team")} className="mt-5" />
        <p className="text-subtle mx-auto mt-2.5 max-w-md text-xs leading-relaxed text-pretty">
          {t("teamHint")}
        </p>
      </div>

      <div className="chat-prompt-shortcuts stagger mt-7 grid gap-2.5 sm:grid-cols-2">
        {PROMPTS.map((p) => (
          <button
            key={p.key}
            type="button"
            onClick={() => onPick(t(`${p.key}Prompt`))}
            className={`group role-${p.role} panel panel-interactive flex items-center gap-3 px-3.5 py-3 text-left`}
          >
            <span className="icon-chip h-9 w-9">
              <p.icon className="h-4 w-4" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="text-foreground block text-sm font-medium">
                {t(`${p.key}Title`)}
              </span>
              <span className="text-muted-foreground block truncate text-xs">
                {t(`${p.key}Hint`)}
              </span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
