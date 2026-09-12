import Link from "next/link";
import { useTranslations } from "next-intl";
import { BookOpen, Database, MessageSquare, Settings } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { ROUTES } from "@/lib/constants";
import { cn } from "@/lib/utils";

interface Action {
  labelKey: string;
  icon: LucideIcon;
  href: string;
  external?: boolean;
  featured?: boolean;
}

const ACTIONS: Action[] = [
  { labelKey: "startChat", icon: MessageSquare, href: ROUTES.CHAT, featured: true },
  { labelKey: "knowledgeStatus", icon: Database, href: ROUTES.RAG },
  { labelKey: "settings", icon: Settings, href: ROUTES.SETTINGS },
  { labelKey: "help", icon: BookOpen, href: ROUTES.HELP },
];

export function QuickActions() {
  const t = useTranslations("dashboard");
  return (
    <div className="border-border bg-card rounded-xl border p-4 sm:p-5">
      <h2 className="text-foreground/55 mb-2.5 font-mono text-[11px] tracking-wider uppercase">
        {t("quickActions")}
      </h2>
      <div className="flex flex-wrap gap-1.5">
        {ACTIONS.map((action) => (
          <ActionPill key={action.labelKey} action={action} label={t(action.labelKey)} />
        ))}
      </div>
    </div>
  );
}

function ActionPill({ action, label }: { action: Action; label: string }) {
  const inner = (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
        action.featured
          ? "bg-foreground text-background border-foreground hover:bg-foreground/90"
          : "border-foreground/15 text-foreground hover:border-foreground/40 hover:bg-foreground/[0.04]",
      )}
    >
      <action.icon className="h-3.5 w-3.5 shrink-0" />
      {label}
    </span>
  );

  if (action.external) {
    return (
      <a href={action.href} target="_blank" rel="noopener noreferrer">
        {inner}
      </a>
    );
  }
  return <Link href={action.href}>{inner}</Link>;
}
