import {
  BookOpen,
  Brain,
  Cpu,
  Database,
  LayoutDashboard,
  MessageSquare,
  Plug,
  Settings,
  ShieldCheck,
  UserCircle,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { isRouteActive, stripLocale } from "@/lib/active-route";
import { ROUTES } from "@/lib/constants";

/** Keys in the `nav` message namespace. */
export type NavKey =
  | "dashboard"
  | "knowledge"
  | "chat"
  | "memory"
  | "tools"
  | "mcp"
  | "skills"
  | "models"
  | "settings"
  | "admin"
  | "profile";

export interface NavItem {
  key: NavKey;
  href: string;
  icon: LucideIcon;
  adminOnly?: boolean;
}

export interface NavGroup {
  labelKey: "groupWorkspace" | "groupManage";
  items: NavItem[];
}

/** Single source for the sidebar, header section label, tab bar and command palette. */
export const NAV_GROUPS: NavGroup[] = [
  {
    labelKey: "groupWorkspace",
    items: [
      { key: "dashboard", href: ROUTES.DASHBOARD, icon: LayoutDashboard },
      { key: "knowledge", href: "/knowledge", icon: Database },
      { key: "chat", href: ROUTES.CHAT, icon: MessageSquare },
      { key: "memory", href: "/memory", icon: Brain },
    ],
  },
  {
    labelKey: "groupManage",
    items: [
      { key: "tools", href: "/tools", icon: Wrench },
      { key: "mcp", href: "/mcp", icon: Plug },
      { key: "skills", href: "/skills", icon: BookOpen },
      { key: "models", href: "/models", icon: Cpu },
    ],
  },
];

export const NAV_FOOTER: NavItem[] = [
  { key: "admin", href: ROUTES.ADMIN, icon: ShieldCheck, adminOnly: true },
  { key: "settings", href: ROUTES.SETTINGS, icon: Settings },
];

const PROFILE_ITEM: NavItem = { key: "profile", href: ROUTES.PROFILE, icon: UserCircle };

export const ALL_NAV_ITEMS: NavItem[] = [
  ...NAV_GROUPS.flatMap((g) => g.items),
  ...NAV_FOOTER,
  PROFILE_ITEM,
];

/** Bottom tab bar on phones: the three daily destinations, search, then settings. */
export const MOBILE_TAB_KEYS: NavKey[] = ["knowledge", "chat", "dashboard"];

export function navItem(key: NavKey): NavItem {
  const item = ALL_NAV_ITEMS.find((i) => i.key === key);
  if (!item) throw new Error(`Unknown nav item: ${key}`);
  return item;
}

/** Which nav entry owns `pathname`; the dashboard is the fallback. */
export function activeNavKey(pathname: string): NavKey {
  const path = stripLocale(pathname);
  const match = ALL_NAV_ITEMS.find(
    (item) => item.key !== "dashboard" && isRouteActive(path, item.href),
  );
  return match?.key ?? "dashboard";
}
