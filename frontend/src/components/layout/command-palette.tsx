"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import {
  Activity,
  ArrowRight,
  LifeBuoy,
  LogOut,
  MessageSquare,
  Palette,
  Plus,
  Search,
  Shield,
  Slash,
  Star,
  UserCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { useAuth } from "@/hooks";
import { conversationListQuery } from "@/hooks/use-conversations";
import { ROUTES } from "@/lib/constants";
import { NAV_GROUPS } from "@/lib/navigation";
import { isAppAdmin } from "@/lib/utils";

export function CommandPalette() {
  const router = useRouter();
  const t = useTranslations("nav");
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  // Same cache entry as the conversation sidebar, so chats started this session show up.
  const recent = useQuery({ ...conversationListQuery(), enabled: open && !!user });
  const conversations = (recent.data ?? []).filter((c) => !c.is_archived);

  // Global ⌘K / Ctrl+K shortcut + a custom event so UI buttons can open it.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    const openHandler = () => setOpen(true);
    document.addEventListener("keydown", handler);
    window.addEventListener("command-palette:open", openHandler);
    return () => {
      document.removeEventListener("keydown", handler);
      window.removeEventListener("command-palette:open", openHandler);
    };
  }, []);

  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label={t("commandPalette")}
      shouldFilter
      overlayClassName="bg-background/60 animate-in fade-in-0 fixed inset-0 z-[60] backdrop-blur-sm"
      contentClassName="bg-popover text-popover-foreground animate-in fade-in-0 zoom-in-95 slide-in-from-top-2 fixed left-1/2 top-[12vh] z-[61] w-[min(92vw,640px)] -translate-x-1/2 overflow-hidden rounded-2xl border shadow-[var(--shadow-overlay)]"
    >
      <div className="border-foreground/10 flex items-center gap-3 border-b px-4 py-3">
        <Search className="text-foreground/45 h-4 w-4" />
        <Command.Input
          autoFocus
          value={search}
          onValueChange={setSearch}
          placeholder={t("searchPlaceholder")}
          className="text-foreground placeholder:text-foreground/45 flex-1 bg-transparent text-sm outline-none"
        />
        <kbd className="border-foreground/15 text-foreground/55 hidden rounded-md border px-1.5 py-0.5 font-mono text-[10px] sm:inline-block">
          ESC
        </kbd>
      </div>

      <Command.List className="max-h-[60vh] overflow-y-auto px-2 py-2">
        <Command.Empty className="text-foreground/55 px-4 py-10 text-center text-sm">
          {t("noMatches")}
        </Command.Empty>

        <Group heading={t("quickActions")}>
          <PaletteItem icon={Plus} label={t("startNewChat")} onSelect={() => go("/chat?new=1")} />
          <PaletteItem
            icon={LifeBuoy}
            label={t("help")}
            onSelect={() => {
              setOpen(false);
              window.open(ROUTES.HELP, "_blank", "noopener");
            }}
          />
        </Group>

        {conversations.length > 0 && (
          <Group heading={t("recentConversations")}>
            {conversations.slice(0, 8).map((c) => (
              <PaletteItem
                key={c.id}
                icon={MessageSquare}
                label={c.title?.trim() || t("untitledConversation")}
                onSelect={() => go(`${ROUTES.CHAT}?id=${c.id}`)}
              />
            ))}
          </Group>
        )}

        {NAV_GROUPS.map((group) => (
          <Group key={group.labelKey} heading={t(group.labelKey)}>
            {group.items.map((item) => (
              <PaletteItem
                key={item.key}
                icon={item.icon}
                label={t(item.key)}
                onSelect={() => go(item.href)}
              />
            ))}
          </Group>
        ))}

        <Group heading={t("settingsSection")}>
          <PaletteItem
            icon={UserCircle}
            label={t("profile")}
            onSelect={() => go(ROUTES.SETTINGS_PROFILE)}
          />
          <PaletteItem
            icon={Shield}
            label={t("account")}
            onSelect={() => go(ROUTES.SETTINGS_ACCOUNT)}
          />
          <PaletteItem
            icon={Palette}
            label={t("appearance")}
            onSelect={() => go(ROUTES.SETTINGS_APPEARANCE)}
          />
          <PaletteItem
            icon={Slash}
            label={t("slashCommands")}
            onSelect={() => go(ROUTES.SETTINGS_SLASH_COMMANDS)}
          />
        </Group>
        {isAppAdmin(user) && (
          <Group heading={t("admin")}>
            <PaletteItem
              icon={Star}
              label={t("responseRatings")}
              onSelect={() => go(ROUTES.ADMIN_RATINGS)}
            />
            <PaletteItem
              icon={Activity}
              label={t("allConversations")}
              onSelect={() => go(ROUTES.ADMIN_CONVERSATIONS)}
            />
          </Group>
        )}

        <Group heading={t("account")}>
          <PaletteItem
            icon={LogOut}
            label={t("logout")}
            onSelect={() => {
              setOpen(false);
              logout();
            }}
          />
        </Group>
      </Command.List>

      <div className="border-foreground/10 text-foreground/45 flex items-center justify-between border-t px-4 py-2 font-mono text-[10px] tracking-wider uppercase">
        <span className="inline-flex items-center gap-1.5">
          <kbd className="border-foreground/15 rounded border px-1 py-0.5">↑↓</kbd>
          {t("paletteMove")}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <kbd className="border-foreground/15 rounded border px-1 py-0.5">↵</kbd>
          {t("paletteOpen")}
        </span>
      </div>
    </Command.Dialog>
  );
}

function Group({ heading, children }: { heading: string; children: React.ReactNode }) {
  return (
    <Command.Group
      heading={heading}
      className="[&_[cmdk-group-heading]]:text-foreground/45 [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:pb-1.5 [&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:uppercase"
    >
      {children}
    </Command.Group>
  );
}

function PaletteItem({
  icon: Icon,
  label,
  onSelect,
  shortcut,
}: {
  icon: LucideIcon;
  label: string;
  onSelect: () => void;
  shortcut?: string;
}) {
  return (
    <Command.Item
      onSelect={onSelect}
      className="group text-foreground/85 hover:bg-foreground/5 data-[selected=true]:bg-brand/10 data-[selected=true]:text-foreground flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors"
    >
      <Icon className="group-data-[selected=true]:text-brand h-4 w-4 shrink-0 opacity-80" />
      <span className="flex-1 truncate">{label}</span>
      {shortcut ? (
        <kbd className="border-foreground/15 text-foreground/55 rounded border px-1.5 py-0.5 font-mono text-[10px]">
          {shortcut}
        </kbd>
      ) : (
        <ArrowRight className="text-foreground/40 h-3.5 w-3.5 opacity-0 transition-opacity group-data-[selected=true]:opacity-100" />
      )}
    </Command.Item>
  );
}
