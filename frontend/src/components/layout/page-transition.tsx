"use client";

import { usePathname } from "next/navigation";

import { stripLocale } from "@/lib/active-route";
import { cn } from "@/lib/utils";

/**
 * Replays the route entrance when the top-level section changes. Keyed on the
 * first path segment so nested layouts (settings, admin) keep their state when
 * moving between their own tabs. Chat is excluded: it hosts fixed side panels
 * that must not sit inside a transformed ancestor while the animation runs.
 */
export function PageTransition({ children }: { children: React.ReactNode }) {
  const section = stripLocale(usePathname() ?? "/").split("/")[1] || "dashboard";

  return (
    <div
      key={section}
      className={cn("console-page flex min-h-0 flex-1 flex-col", section !== "chat" && "page-enter")}
    >
      {children}
    </div>
  );
}
