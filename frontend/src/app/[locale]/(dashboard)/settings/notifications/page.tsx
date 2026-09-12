"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale } from "next-intl";
import { CreditCard, MessageSquare, Sparkles, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { toast } from "sonner";

import { Button, Switch } from "@/components/ui";
import { SectionCard } from "@/components/settings/settings-section";

interface NotificationCategory {
  key: string;
  label: string;
  description: string;
  icon: LucideIcon;
  /** Default values for new users. */
  defaults: { email: boolean; inApp: boolean };
}

const CATEGORIES: NotificationCategory[] = [
  {
    key: "billing",
    label: "Billing",
    description: "Subscription renewals, payment failures, low credit warnings.",
    icon: CreditCard,
    defaults: { email: true, inApp: true },
  },
  {
    key: "members",
    label: "Team activity",
    description: "Invitations accepted, members joining or leaving your workspace.",
    icon: Users,
    defaults: { email: true, inApp: true },
  },
  {
    key: "security",
    label: "Security alerts",
    description: "New device sign-ins, password changes, suspicious activity.",
    icon: MessageSquare,
    defaults: { email: true, inApp: true },
  },
  {
    key: "product",
    label: "Product updates",
    description: "New features, release notes, occasional how-to tips.",
    icon: Sparkles,
    defaults: { email: false, inApp: true },
  },
];

const STORAGE_KEY = "settings.notifications.prefs";

type Prefs = Record<string, { email: boolean; inApp: boolean }>;

function defaultPrefs(): Prefs {
  return Object.fromEntries(
    CATEGORIES.map((c) => [c.key, { email: c.defaults.email, inApp: c.defaults.inApp }]),
  );
}

function loadPrefs(): Prefs {
  if (typeof window === "undefined") return defaultPrefs();
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultPrefs();
    return { ...defaultPrefs(), ...(JSON.parse(raw) as Prefs) };
  } catch {
    return defaultPrefs();
  }
}

function savePrefs(prefs: Prefs) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
}

export default function NotificationsSettingsPage() {
  const locale = useLocale();
  const isZh = locale === "zh";
  const categoryCopy: Record<string, { label: string; description: string }> = isZh
    ? {
        billing: { label: "账单", description: "订阅续费、付款失败和积分不足提醒。" },
        members: { label: "团队动态", description: "邀请接受、成员加入或离开工作区。" },
        security: { label: "安全提醒", description: "新设备登录、密码更改和可疑活动。" },
        product: { label: "产品更新", description: "新功能、版本更新和使用技巧。" },
      }
    : Object.fromEntries(CATEGORIES.map((c) => [c.key, { label: c.label, description: c.description }]));
  const [prefs, setPrefs] = useState<Prefs>(defaultPrefs);
  const [dirty, setDirty] = useState(false);
  const initialPrefs = useMemo(loadPrefs, []);

  useEffect(() => {
    setPrefs(initialPrefs);
  }, [initialPrefs]);

  const toggle = (key: string, channel: "email" | "inApp") => {
    setPrefs((prev) => ({
      ...prev,
      [key]: {
        email: prev[key]?.email ?? true,
        inApp: prev[key]?.inApp ?? true,
        [channel]: !(prev[key]?.[channel] ?? true),
      },
    }));
    setDirty(true);
  };

  const handleSave = () => {
    savePrefs(prefs);
    toast.success(isZh ? "通知偏好已保存" : "Notification preferences saved");
    setDirty(false);
  };

  const handleReset = () => {
    setPrefs(defaultPrefs());
    setDirty(true);
  };

  return (
    <div className="space-y-6">
      <SectionCard
        title={isZh ? "通知偏好" : "Notification preferences"}
        description={isZh ? "选择通过邮件发送或仅在应用内显示的通知类型。" : "Choose which events are sent by email or shown only in the app."}
        action={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={handleReset}>
              {isZh ? "恢复默认" : "Reset to defaults"}
            </Button>
            <Button onClick={handleSave} disabled={!dirty} size="sm">
              {isZh ? "保存更改" : "Save changes"}
            </Button>
          </div>
        }
      >
        <div className="border-border overflow-hidden rounded-xl border">
          <div className="border-border bg-muted grid grid-cols-[1fr_70px_70px] items-center gap-2 border-b px-5 py-3 sm:grid-cols-[1.5fr_90px_90px]">
            <span className="text-muted-foreground text-[11px] font-medium tracking-wide uppercase">
              {isZh ? "类别" : "Category"}
            </span>
            <span className="text-muted-foreground text-center text-[11px] font-medium tracking-wide uppercase">
              {isZh ? "邮件" : "Email"}
            </span>
            <span className="text-muted-foreground text-center text-[11px] font-medium tracking-wide uppercase">
              {isZh ? "应用内" : "In-app"}
            </span>
          </div>
          <ul className="divide-border divide-y">
            {CATEGORIES.map((c) => {
              const p = prefs[c.key] ?? c.defaults;
              const copy = categoryCopy[c.key] ?? { label: c.label, description: c.description };
              return (
                <li
                  key={c.key}
                  className="hover:bg-accent grid grid-cols-[1fr_70px_70px] items-center gap-2 px-5 py-4 transition-colors sm:grid-cols-[1.5fr_90px_90px]"
                >
                  <div className="flex min-w-0 items-start gap-3">
                    <span className="bg-muted text-muted-foreground inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg">
                      <c.icon className="h-4 w-4" />
                    </span>
                    <div className="min-w-0">
                      <p className="text-foreground text-sm font-medium">{copy.label}</p>
                      <p className="text-muted-foreground mt-0.5 text-xs leading-relaxed">
                        {copy.description}
                      </p>
                    </div>
                  </div>
                  <div className="flex justify-center">
                    <Switch
                      checked={p.email}
                      onCheckedChange={() => toggle(c.key, "email")}
                      aria-label={isZh ? `${copy.label}邮件通知` : `Email notifications for ${copy.label}`}
                    />
                  </div>
                  <div className="flex justify-center">
                    <Switch
                      checked={p.inApp}
                      onCheckedChange={() => toggle(c.key, "inApp")}
                      aria-label={isZh ? `${copy.label}应用内通知` : `In-app notifications for ${copy.label}`}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
        <p className="text-muted-foreground mt-4 text-xs leading-relaxed">
          {locale === "zh"
            ? "通知偏好当前保存在此设备上。"
            : "Notification preferences are currently stored on this device."}
        </p>
      </SectionCard>
    </div>
  );
}
