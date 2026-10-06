"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Search } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { isRouteActive, stripLocale } from "@/lib/active-route";
import { MOBILE_TAB_KEYS, navItem } from "@/lib/navigation";
import { cn } from "@/lib/utils";

interface TabItem {
  label: string;
  href?: string;
  icon: LucideIcon;
  /** When true, treat as active if pathname starts with `href`. */
  startsWith?: boolean;
  /** Prefix used for the active state when it differs from `href`. */
  match?: string;
  onClick?: () => void;
}

export function MobileTabBar() {
  const pathname = usePathname();
  const router = useRouter();
  const t = useTranslations("nav");

  const stripped = stripLocale(pathname);

  const settings = navItem("settings");
  const items: TabItem[] = [
    ...MOBILE_TAB_KEYS.map((key) => {
      const item = navItem(key);
      return { label: t(key), href: item.href, icon: item.icon, startsWith: key !== "dashboard" };
    }),
    {
      label: t("search"),
      icon: Search,
      onClick: () => window.dispatchEvent(new CustomEvent("command-palette:open")),
    },
    { label: t("settings"), href: settings.href, match: settings.match, icon: settings.icon, startsWith: true },
  ];

  const isActive = (item: TabItem) =>
    !!item.href && isRouteActive(stripped, item.match ?? item.href, !item.startsWith);

  return (
    <nav
      role="navigation"
      aria-label={t("mobileNav")}
      className="bg-background/90 supports-[backdrop-filter]:bg-background/75 fixed inset-x-0 bottom-0 z-40 flex items-stretch justify-around border-t pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden"
    >
      {items.map((item) => {
        const active = isActive(item);
        const className = cn(
          "flex min-h-[56px] flex-1 flex-col items-center justify-center gap-1 py-2 text-2xs font-medium transition-colors",
          active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
        );
        const inner = (
          <>
            <item.icon
              className={cn("h-5 w-5 transition-transform", active && "text-brand -translate-y-px")}
            />
            <span>{item.label}</span>
            {active && (
              <span aria-hidden className="bg-brand pop-in absolute top-0 h-0.5 w-8 rounded-sm" />
            )}
          </>
        );
        if (item.onClick) {
          return (
            <button
              key={item.label}
              type="button"
              onClick={item.onClick}
              aria-label={item.label}
              className={cn(className, "relative")}
            >
              {inner}
            </button>
          );
        }
        return (
          <Link
            key={item.label}
            href={item.href!}
            aria-label={item.label}
            aria-current={active ? "page" : undefined}
            className={cn(className, "relative")}
            onClick={(e) => {
              if (item.href === stripped) {
                e.preventDefault();
                router.refresh();
              }
            }}
          >
            {inner}
          </Link>
        );
      })}
    </nav>
  );
}
