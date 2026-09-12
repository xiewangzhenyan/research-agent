"use client";

import type { ReactNode } from "react";
import { Activity, LayoutDashboard, MessageSquare, Star, Users } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/dashboard/page-header";
import { PageTabs, type PageTab } from "@/components/dashboard/page-tabs";

const ADMIN_TABS = [
  { labelKey: "overview", href: ROUTES.ADMIN, icon: LayoutDashboard, exact: true },
  { labelKey: "users", href: ROUTES.ADMIN_USERS, icon: Users },
  { labelKey: "conversations", href: ROUTES.ADMIN_CONVERSATIONS, icon: MessageSquare },
  { labelKey: "ratings", href: ROUTES.ADMIN_RATINGS, icon: Star },
  { labelKey: "system", href: ROUTES.ADMIN_SYSTEM, icon: Activity },
];

export default function AdminLayout({ children }: { children: ReactNode }) {
  const t = useTranslations("nav");
  const isZh = useLocale() === "zh";
  const tabs: PageTab[] = ADMIN_TABS.map((tab) => ({ ...tab, label: t(tab.labelKey) }));
  return (
    <div className="space-y-6 pb-8">
      <PageHeader
        eyebrow={t("admin")}
        title={isZh ? "工作区管理" : "Workspace administration"}
        description={isZh ? "管理用户、对话、回复评分和系统运行状态。" : "Manage users, conversations, response ratings, and system health."}
      />
      <PageTabs tabs={tabs} />
      <div className="min-w-0">{children}</div>
    </div>
  );
}
