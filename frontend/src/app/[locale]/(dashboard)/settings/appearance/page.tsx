"use client";

import { useLocale } from "next-intl";
import { SectionCard } from "@/components/settings/settings-section";
import { ThemeToggle } from "@/components/theme";

export default function AppearanceSettingsPage() {
  const isZh = useLocale() === "zh";
  return (
    <div className="space-y-6">
      <SectionCard
        title={isZh ? "主题" : "Theme"}
        description={isZh ? "选择浅色、深色或跟随系统设置。" : "Light, dark, or follow your system preference."}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-foreground text-sm font-medium">{isZh ? "配色方案" : "Color scheme"}</p>
            <p className="text-muted-foreground mt-0.5 text-xs leading-relaxed">
              {isZh ? "此设置会应用到整个控制台。" : "This setting applies to the entire dashboard."}
            </p>
          </div>
          <div className="shrink-0">
            <ThemeToggle variant="dropdown" />
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
