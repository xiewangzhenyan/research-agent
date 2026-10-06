"use client";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { MessageSquare } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { apiClient } from "@/lib/api-client";
import { ROUTES } from "@/lib/constants";
import { currentProject } from "@/lib/project-scope";
import { cn, getErrorMessage, timeAgo } from "@/lib/utils";
import { useAuthStore } from "@/stores";
interface ActivityItem {
  id: string;
  icon: LucideIcon;
  title: string;
  description?: string;
  timestamp: string;
  href?: string;
  accent?: "default" | "brand" | "danger";
}
interface ConversationItem {
  id: string;
  title?: string | null;
  created_at: string;
  updated_at?: string | null;
}

/**
 * The five latest conversations plus the total count. Shared by the overview's
 * stat card and this list so the dashboard makes one request; revisits render
 * from cache at once and refresh in the background.
 */
export function useRecentConversations() {
  const userId = useAuthStore((s) => s.user?.id);
  return useQuery({
    queryKey: ["conversations", "recent", userId, currentProject()?.id ?? "default"],
    queryFn: () =>
      apiClient.get<{ items: ConversationItem[]; total: number }>("/conversations?limit=5"),
    enabled: !!userId,
    staleTime: 0,
  });
}

export function RecentActivity({ limit = 6 }: { limit?: number }) {
  const t = useTranslations("dashboard");
  const locale = useLocale();
  const recent = useRecentConversations();
  const error = recent.isError ? getErrorMessage(recent.error, t("activityLoadFailed")) : null;
  const items: ActivityItem[] | null = recent.data
    ? recent.data.items
        .slice(0, 4)
        .map((c) => ({
          id: `conv-${c.id}`,
          icon: MessageSquare,
          title: c.title?.trim() || t("newConversation"),
          description: t("conversation"),
          timestamp: c.updated_at || c.created_at,
          href: `${ROUTES.CHAT}?id=${c.id}`,
        }))
        .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
        .slice(0, limit)
    : null;

  return (
    <div className="panel flex h-full min-w-0 flex-col p-5 lg:p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-display text-foreground text-base font-semibold">
          {t("recentActivity")}
        </h2>
        <Link
          href={ROUTES.CHAT}
          className="text-foreground/55 hover:text-foreground font-mono text-[11px] tracking-wider uppercase"
        >
          {t("viewAll")} →
        </Link>
      </div>

      {items === null && !error && <LoadingState variant="skeleton-list" rows={4} />}
      {error && (
        <ErrorState
          title={t("activityLoadFailed")}
          description={error}
          cta={{ label: t("retry"), onClick: () => void recent.refetch() }}
        />
      )}
      {items && items.length === 0 && !error && (
        <EmptyState
          icon={MessageSquare}
          title={t("nothingYet")}
          description={t("emptyActivity")}
          cta={{ label: t("startChat"), href: ROUTES.CHAT }}
          fill
          className="border-0 bg-transparent py-8"
        />
      )}
      {items && items.length > 0 && (
        <ul className="-mx-2 flex-1 space-y-0.5">
          {items.map((item) => (
            <li key={item.id}>
              <ActivityRow item={item} locale={locale} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ActivityRow({ item, locale }: { item: ActivityItem; locale: string }) {
  const content = (
    <div
      className={cn(
        "hover:bg-foreground/[0.04] flex items-start gap-3 rounded-xl px-2 py-2.5 transition-colors",
      )}
    >
      <div
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-sm",
          item.accent === "brand"
            ? "bg-muted text-foreground"
            : item.accent === "danger"
              ? "bg-destructive/10 text-destructive"
              : "bg-foreground/8 text-foreground/80",
        )}
      >
        <item.icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-foreground truncate text-sm font-medium">{item.title}</p>
        <p className="text-foreground/55 truncate text-xs">
          {item.description}
          {item.description && " · "}
          {timeAgo(item.timestamp, locale)}
        </p>
      </div>
    </div>
  );

  if (item.href) {
    return <Link href={item.href}>{content}</Link>;
  }
  return content;
}
