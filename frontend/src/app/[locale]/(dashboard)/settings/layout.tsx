"use client";

import type { ReactNode } from "react";
import { Palette, Shield, Slash, UserCircle } from "lucide-react";
import Link from "next/link";
import { useActiveRoute } from "@/lib/active-route";
import { useLocale, useTranslations } from "next-intl";

import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/dashboard/page-header";

const SETTINGS_TABS = [
  { labelKey: "profile", href: ROUTES.SETTINGS_PROFILE, icon: UserCircle },
  { labelKey: "account", href: ROUTES.SETTINGS_ACCOUNT, icon: Shield },
  { labelKey: "slashCommands", href: ROUTES.SETTINGS_SLASH_COMMANDS, icon: Slash },
  { labelKey: "appearance", href: ROUTES.SETTINGS_APPEARANCE, icon: Palette },
];

export default function SettingsLayout({ children }: { children: ReactNode }) {
  const t = useTranslations("nav");
  const isZh = useLocale() === "zh";
  const active = useActiveRoute();
  const tabs = SETTINGS_TABS.map((tab) => ({ ...tab, label: t(tab.labelKey) }));
  return (
    <div className="console-settings w-full space-y-6 pb-8">
      <PageHeader
        eyebrow={t("settings")}
        title={t("settings")}
        description={
          isZh
            ? "管理个人资料、账户安全、外观和斜杠命令。"
            : "Manage your profile, account security, appearance and slash commands."
        }
      />
      <div className="console-settings-grid">
        <nav
          className="console-settings-nav"
          aria-label={isZh ? "设置分类" : "Settings categories"}
        >
          {tabs.map((tab) => (
            <Link
              key={tab.href}
              href={tab.href}
              aria-current={active(tab.href) ? "page" : undefined}
            >
              <tab.icon size={16} />
              {tab.label}
            </Link>
          ))}
        </nav>
        <div className="min-w-0">{children}</div>
      </div>
    </div>
  );
}
