"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { ChevronDown, History, LogOut, Menu, Search, Settings, UserCircle } from "lucide-react";
import { LanguageSwitcherIcon } from "@/components/language-switcher";
import { ThemeToggle } from "@/components/theme";
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui";
import { useAuth } from "@/hooks";
import { usePathname } from "next/navigation";
import { stripLocale } from "@/lib/active-route";
import { ROUTES } from "@/lib/constants";
import { useAuthStore, useSidebarStore, useChatSidebarStore } from "@/stores";

export function Header() {
  const { user, isAuthenticated, logout } = useAuth();
  const avatarVersion = useAuthStore((s) => s.avatarVersion);
  const { toggle } = useSidebarStore();
  const openHistory = useChatSidebarStore((s) => s.open);
  const pathname = stripLocale(usePathname());
  const zh = useLocale() === "zh";
  const t = useTranslations("nav");
  const tc = useTranslations("common");
  const section = pathname.startsWith("/tools")
    ? zh
      ? "工具中心"
      : "Tools"
    : pathname.startsWith("/tasks")
      ? zh
        ? "后台任务"
        : "Tasks"
      : pathname.startsWith("/models")
        ? zh
          ? "模型与能力"
          : "Models and capabilities"
        : pathname.startsWith("/knowledge")
          ? t("knowledge")
          : pathname.startsWith("/chat")
            ? t("chat")
            : pathname.startsWith("/settings")
              ? t("settings")
              : pathname.startsWith("/admin")
                ? t("admin")
                : pathname.startsWith("/profile")
                  ? t("profile")
                  : t("dashboard");

  const openSearch = () => window.dispatchEvent(new CustomEvent("command-palette:open"));

  return (
    <header className="console-topbar">
      <div className="flex h-16 items-center justify-between gap-2 px-3 sm:px-6">
        <div className="flex items-center gap-1 sm:gap-3">
          <Button variant="ghost" size="sm" className="h-9 w-9 p-0 lg:hidden" onClick={toggle}>
            <Menu className="h-5 w-5" />
            <span className="sr-only">{t("toggleMenu")}</span>
          </Button>

          <div className="flex items-center gap-3 text-sm">
            <span className="text-muted-foreground hidden sm:inline">
              {zh ? "工作台" : "Workspace"}
            </span>
            <span className="text-muted-foreground hidden sm:inline" aria-hidden>
              /
            </span>
            <span className="font-medium">{section}</span>
          </div>
        </div>

        <div className="flex items-center gap-1">
          {pathname.startsWith("/chat") && (
            <Button
              variant="ghost"
              size="icon"
              className="h-9 w-9 lg:hidden"
              onClick={openHistory}
              aria-label={zh ? "历史对话" : "Chat history"}
            >
              <History size={18} />
            </Button>
          )}
          <button
            onClick={openSearch}
            aria-label={tc("search")}
            title={`${tc("search")} (⌘K)`}
            className="console-search-trigger"
          >
            <Search className="h-[1.1rem] w-[1.1rem]" />
            <span className="hidden md:inline">{tc("search")}</span>
            <kbd className="hidden md:inline">⌘ K</kbd>
          </button>
          <div className="ml-0.5 hidden items-center sm:flex">
            <LanguageSwitcherIcon />
          </div>
          <ThemeToggle className="text-muted-foreground hover:text-foreground hover:bg-accent h-9 w-9 rounded-lg [&_svg]:size-[1.1rem]" />

          {isAuthenticated && <div className="bg-border mx-1.5 hidden h-5 w-px sm:block" />}

          {isAuthenticated ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  aria-label={zh ? "账号菜单" : "Account menu"}
                  className="hover:bg-accent focus-visible:ring-ring ml-0.5 flex items-center gap-1.5 rounded-full p-0.5 pr-2 transition-colors outline-none focus-visible:ring-1"
                >
                  <Avatar className="h-7 w-7">
                    {user?.avatar_url && (
                      <AvatarImage
                        src={`/api/users/avatar/${user.id}?v=${avatarVersion}`}
                        alt={user.email}
                      />
                    )}
                    <AvatarFallback className="bg-foreground text-background text-[10px] font-semibold">
                      {user?.email?.substring(0, 2).toUpperCase() || "U"}
                    </AvatarFallback>
                  </Avatar>
                  <ChevronDown className="text-muted-foreground h-3 w-3" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel className="flex flex-col">
                  <span className="truncate text-sm font-semibold">
                    {user?.full_name || user?.email?.split("@")[0]}
                  </span>
                  <span className="text-muted-foreground truncate text-xs font-normal">
                    {user?.email}
                  </span>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem asChild>
                  <Link href={ROUTES.PROFILE}>
                    <UserCircle className="mr-2 h-4 w-4" />
                    {t("profile")}
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link href={ROUTES.SETTINGS}>
                    <Settings className="mr-2 h-4 w-4" />
                    {t("settings")}
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={logout}
                  className="text-destructive focus:text-destructive"
                >
                  <LogOut className="mr-2 h-4 w-4" />
                  {t("logout")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <div className="ml-1 flex items-center gap-1.5">
              <Button variant="ghost" size="sm" asChild className="h-9 rounded-lg">
                <Link href={ROUTES.LOGIN}>{t("login")}</Link>
              </Button>
              <Button size="sm" asChild className="h-9 rounded-lg">
                <Link href={ROUTES.REGISTER}>{t("register")}</Link>
              </Button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
