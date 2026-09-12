"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useLocale, useTranslations } from "next-intl";
import {
  Cpu,
  Wrench,
  ListTodo,
  Database,
  LayoutDashboard,
  MessageSquare,
  Settings,
  ShieldCheck,
  ArrowUpRight,
  Plus,
} from "lucide-react";
import { useActiveRoute } from "@/lib/active-route";
import { cn, isAppAdmin } from "@/lib/utils";
import { APP_BRAND, APP_NAME, ROUTES } from "@/lib/constants";
import { ResearchMark } from "@/components/brand/research-mark";
import { useSidebarStore, useAuthStore } from "@/stores";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetClose } from "@/components/ui";

const ConversationSidebar = dynamic(
  () => import("@/components/chat/conversation-sidebar").then((m) => m.ConversationSidebar),
  { ssr: false },
);

const navigation = [
  { nameKey: "dashboard", href: ROUTES.DASHBOARD, icon: LayoutDashboard },
  { nameKey: "knowledge", href: "/knowledge", icon: Database },
  { nameKey: "chat", href: ROUTES.CHAT, icon: MessageSquare },
];
function SidebarContents({
  onNavigate,
  history = false,
}: {
  onNavigate?: () => void;
  history?: boolean;
}) {
  const active = useActiveRoute();
  const user = useAuthStore((s) => s.user);
  const t = useTranslations("nav");
  const zh = useLocale() === "zh";
  const linkStyle = (href: string) => cn("console-nav-link", active(href) && "is-active");
  return (
    <>
      <Link href={ROUTES.DASHBOARD} onClick={onNavigate} className="console-brand">
        <ResearchMark size={35} className="shrink-0" />
        <span>
          {APP_NAME}
          <small>
            {APP_BRAND} · {zh ? "科研工作空间" : "Research workspace"}
          </small>
        </span>
      </Link>
      <div className="px-4 pt-2">
        <Link href="/chat" onClick={onNavigate} className="workspace-new-chat">
          <Plus size={18} />
          {zh ? "开始对话" : "Start a conversation"}
        </Link>
      </div>
      <div className="px-4 pt-6">
        <p className="console-nav-caption">{zh ? "工作空间" : "WORKSPACE"}</p>
      </div>
      <nav aria-label={zh ? "工作台导航" : "Workspace navigation"} className="space-y-1 px-3 pt-3">
        {navigation.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={active(item.href) ? "page" : undefined}
            className={linkStyle(item.href)}
          >
            <item.icon size={18} />
            {t(item.nameKey)}
          </Link>
        ))}
        <Link
          href="/tasks"
          onClick={onNavigate}
          aria-current={active("/tasks") ? "page" : undefined}
          className={linkStyle("/tasks")}
        >
          <ListTodo size={18} />
          {zh ? "后台任务" : "Tasks"}
        </Link>
        <p className="console-nav-caption pt-6 pb-2">{zh ? "管理" : "MANAGE"}</p>
        <Link
          href="/tools"
          onClick={onNavigate}
          aria-current={active("/tools") ? "page" : undefined}
          className={linkStyle("/tools")}
        >
          <Wrench size={18} />
          {zh ? "工具中心" : "Tools"}
        </Link>
        <Link
          href="/models"
          onClick={onNavigate}
          aria-current={active("/models") ? "page" : undefined}
          className={linkStyle("/models")}
        >
          <Cpu size={18} />
          {zh ? "模型与能力" : "Models and capabilities"}
        </Link>
      </nav>
      {history && active("/chat") && <ConversationSidebar embedded />}
      <div className="mt-auto space-y-1 p-3">
        {isAppAdmin(user) && (
          <Link
            href={ROUTES.ADMIN}
            onClick={onNavigate}
            className={linkStyle(ROUTES.ADMIN)}
            aria-current={active(ROUTES.ADMIN) ? "page" : undefined}
          >
            <ShieldCheck size={18} />
            {t("admin")}
          </Link>
        )}
        <Link
          href={ROUTES.SETTINGS}
          onClick={onNavigate}
          className={linkStyle(ROUTES.SETTINGS)}
          aria-current={active(ROUTES.SETTINGS) ? "page" : undefined}
        >
          <Settings size={18} />
          {t("settings")}
        </Link>
        <div className="console-sidebar-note">
          <Database size={16} />
          <span>{zh ? "知识驱动每一次对话" : "Your own knowledge space"}</span>
        </div>
        <Link
          href="/"
          onClick={onNavigate}
          className="text-muted-foreground flex items-center justify-between px-3 py-2 text-xs"
        >
          {zh ? "返回网站首页" : "Visit website"}
          <ArrowUpRight size={13} />
        </Link>
      </div>
    </>
  );
}
export function Sidebar() {
  const { isOpen, close } = useSidebarStore();
  return (
    <>
      <aside className="console-sidebar hidden lg:flex">
        <SidebarContents history />
      </aside>
      <Sheet
        open={isOpen}
        onOpenChange={(open) => {
          if (!open) close();
        }}
      >
        <SheetContent side="left" className="console-mobile-sidebar flex w-72 flex-col gap-0 p-0">
          <SheetHeader className="sr-only">
            <SheetTitle>{APP_NAME}</SheetTitle>
          </SheetHeader>
          <SheetClose onClick={close} className="absolute top-2 right-2" />
          <SidebarContents onNavigate={close} />
        </SheetContent>
      </Sheet>
    </>
  );
}
