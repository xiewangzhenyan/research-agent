"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";
import { useLayoutEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { ArrowUpRight, Plus } from "lucide-react";

import { ResearchMark } from "@/components/brand/research-mark";
import { useProject } from "@/components/projects/project-provider";
import { Sheet, SheetClose, SheetContent, SheetHeader, SheetTitle } from "@/components/ui";
import { useActiveRoute } from "@/lib/active-route";
import { APP_BRAND, APP_NAME } from "@/lib/constants";
import { NAV_FOOTER, NAV_GROUPS, type NavItem } from "@/lib/navigation";
import { cn, isAppAdmin } from "@/lib/utils";
import { useAuthStore, useSidebarStore } from "@/stores";

const ConversationSidebar = dynamic(
  () => import("@/components/chat/conversation-sidebar").then((m) => m.ConversationSidebar),
  { ssr: false },
);

/** Positions the sliding highlight under the active link of `navRef`. */
function useNavIndicator(navRef: React.RefObject<HTMLElement | null>) {
  const pathname = usePathname();
  const [box, setBox] = useState<{ y: number; h: number } | null>(null);
  const [ready, setReady] = useState(false);

  useLayoutEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    const measure = () => {
      const link = nav.querySelector<HTMLElement>(".console-nav-link.is-active");
      setBox(link ? { y: link.offsetTop, h: link.offsetHeight } : null);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(nav);
    // First placement is instant; later route changes slide.
    const frame = requestAnimationFrame(() => setReady(true));
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [navRef, pathname]);

  return { box, ready };
}

function NavLink({ item, onNavigate }: { item: NavItem; onNavigate?: () => void }) {
  const active = useActiveRoute();
  const t = useTranslations("nav");
  const isActive = active(item.href);
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={isActive ? "page" : undefined}
      className={cn("console-nav-link", isActive && "is-active")}
    >
      <item.icon size={18} strokeWidth={1.9} />
      {t(item.key)}
    </Link>
  );
}

function SidebarContents({
  onNavigate,
  history = false,
}: {
  onNavigate?: () => void;
  history?: boolean;
}) {
  const active = useActiveRoute();
  const workspace = useProject();
  const user = useAuthStore((s) => s.user);
  const t = useTranslations("nav");
  const navRef = useRef<HTMLElement>(null);
  const { box, ready } = useNavIndicator(navRef);

  return (
    <>
      <Link href="/dashboard" onClick={onNavigate} className="console-brand">
        <ResearchMark size={32} className="shrink-0" />
        <span>
          {APP_NAME}
          <small>
            {APP_BRAND} · {t("brandSubtitle")}
          </small>
        </span>
      </Link>
      <div className="px-3">
        <Link href="/chat?new=1" onClick={onNavigate} className="workspace-new-chat">
          <Plus size={18} strokeWidth={2.2} />
          {t("newChat")}
        </Link>
      </div>
      <nav
        ref={navRef}
        aria-label={t("workspaceNav")}
        className={cn("console-nav space-y-5 px-3 pt-6", box && "has-indicator")}
      >
        {box && (
          <span
            aria-hidden
            data-ready={ready || undefined}
            className="console-nav-indicator"
            style={{ transform: `translateY(${box.y}px)`, height: box.h }}
          />
        )}
        {NAV_GROUPS.map((group) => (
          <div key={group.labelKey} className="space-y-0.5">
            <p className="console-nav-caption pb-1.5">{t(group.labelKey)}</p>
            {group.items.map((item) => (
              <NavLink key={item.key} item={item} onNavigate={onNavigate} />
            ))}
          </div>
        ))}
      </nav>
      {workspace?.ready && history && active("/chat") && <ConversationSidebar embedded />}
      <div className="mt-auto space-y-0.5 border-t p-3">
        {NAV_FOOTER.filter((item) => !item.adminOnly || isAppAdmin(user)).map((item) => (
          <NavLink key={item.key} item={item} onNavigate={onNavigate} />
        ))}
        <Link
          href="/"
          onClick={onNavigate}
          className="text-muted-foreground hover:text-foreground flex items-center justify-between rounded-md px-3 py-2 text-xs transition-colors"
        >
          {t("visitWebsite")}
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
        <SheetContent side="left" className="console-mobile-sidebar bg-sidebar flex w-72 flex-col gap-0 p-0">
          <SheetHeader className="sr-only">
            <SheetTitle>{APP_NAME}</SheetTitle>
          </SheetHeader>
          <SheetClose onClick={close} className="absolute top-3 right-2" />
          <SidebarContents onNavigate={close} />
        </SheetContent>
      </Sheet>
    </>
  );
}
