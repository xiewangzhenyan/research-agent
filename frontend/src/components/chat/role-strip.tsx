"use client";

import { useTranslations } from "next-intl";

import { cn } from "@/lib/utils";

export const AGENT_ROLES = ["plan", "research", "write", "review"] as const;
export type AgentRole = (typeof AGENT_ROLES)[number];

interface RoleStripProps {
  /** A relay highlight sweeps across while the run is active. It never claims which role is working. */
  running?: boolean;
  label?: string;
  className?: string;
}

/** The four collaboration roles as one strip, in their fixed order. */
export function RoleStrip({ running = false, label, className }: RoleStripProps) {
  const t = useTranslations("chat.agents");
  return (
    <span className={cn("role-strip", className)} data-running={running || undefined}>
      {label && <span className="text-muted-foreground px-2 text-xs">{label}</span>}
      {AGENT_ROLES.map((role) => (
        <span key={role} className={cn("role-pill", `role-${role}`)}>
          {t(role)}
        </span>
      ))}
    </span>
  );
}
