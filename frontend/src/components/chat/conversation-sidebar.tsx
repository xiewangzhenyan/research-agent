"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useConversations } from "@/hooks";
import { Button, Skeleton } from "@/components/ui";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetClose } from "@/components/ui";
import { cn } from "@/lib/utils";
import { useChatSidebarStore } from "@/stores";
import { Archive, ChevronLeft, ChevronRight, MessageSquare, SquarePen } from "lucide-react";
import type { Conversation } from "@/types";
import { ShareDialog } from "./share-dialog";
import { ConversationItem, type ConversationItemProps } from "./conversation-item";

type ConversationView = "active" | "archived";

interface ConversationListProps {
  conversations: Conversation[];
  currentConversationId: string | null;
  isLoading: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => ReturnType<ConversationItemProps["onDelete"]>;
  onArchive: (id: string) => void;
  onUnarchive: (id: string) => void;
  onRename: (id: string, title: string) => ReturnType<ConversationItemProps["onRename"]>;
  onNewChat: () => void;
  onNavigate?: () => void;
  onLoadMore?: () => void;
}

function ConversationList({
  conversations = [],
  currentConversationId,
  isLoading,
  onSelect,
  onDelete,
  onArchive,
  onUnarchive,
  onRename,
  onNewChat,
  onNavigate,
  onLoadMore,
}: ConversationListProps) {
  const t = useTranslations("chat");
  const [view, setView] = useState<ConversationView>("active");
  const [shareConversationId, setShareConversationId] = useState<string | null>(null);

  const all = conversations ?? [];
  const activeCount = all.filter((c) => !c.is_archived).length;
  const archivedCount = all.filter((c) => c.is_archived).length;
  const visible = all.filter((c) => (view === "active" ? !c.is_archived : c.is_archived));

  const handleSelect = (id: string) => {
    onSelect(id);
    onNavigate?.();
  };

  const handleNewChat = () => {
    onNewChat();
    onNavigate?.();
  };

  const isArchivedView = view === "archived";

  return (
    <>
      <div className="px-3 pt-3 pb-2">
        <button
          type="button"
          onClick={handleNewChat}
          className="text-muted-foreground hover:text-foreground hover:bg-secondary flex h-9 w-full items-center gap-2 rounded-lg px-3 text-sm font-medium transition-colors"
        >
          <SquarePen className="h-4 w-4 shrink-0" />
          {t("newChat")}
        </button>
      </div>

      <div className="px-3 pb-2">
        <div className="bg-secondary/50 flex rounded-lg p-0.5">
          <ViewTab
            label={t("active")}
            count={activeCount}
            active={view === "active"}
            onClick={() => setView("active")}
          />
          <ViewTab
            label={t("archived")}
            count={archivedCount}
            active={view === "archived"}
            onClick={() => setView("archived")}
          />
        </div>
      </div>

      <div
        className="flex-1 scrollbar-thin overflow-y-auto px-3 pb-3"
        onScroll={(e) => {
          const el = e.currentTarget;
          if (!isLoading && el.scrollHeight - el.scrollTop - el.clientHeight < 100) {
            onLoadMore?.();
          }
        }}
      >
        {isLoading && conversations.length === 0 ? (
          <div className="space-y-2 py-2">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-9 w-full rounded-md" />
            ))}
          </div>
        ) : visible.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <span
              aria-hidden
              className="bg-muted text-muted-foreground mb-4 flex h-12 w-12 items-center justify-center rounded-full"
            >
              {isArchivedView ? (
                <Archive className="h-5 w-5" />
              ) : (
                <MessageSquare className="h-5 w-5" />
              )}
            </span>
            <p className="text-foreground text-sm font-medium">
              {isArchivedView ? t("noArchivedConversations") : t("noConversations")}
            </p>
            <p className="text-muted-foreground mt-1 text-xs">
              {isArchivedView ? t("archivedConversationHint") : t("startNewChat")}
            </p>
          </div>
        ) : (
          <div className="space-y-1">
            {visible.map((conversation) => (
              <ConversationItem
                key={conversation.id}
                conversation={conversation}
                isActive={conversation.id === currentConversationId}
                onSelect={() => handleSelect(conversation.id)}
                onDelete={() => onDelete(conversation.id)}
                onArchive={() => onArchive(conversation.id)}
                onUnarchive={() => onUnarchive(conversation.id)}
                onRename={(title) => onRename(conversation.id, title)}
                onShare={() => setShareConversationId(conversation.id)}
              />
            ))}
          </div>
        )}
      </div>
      {shareConversationId && (
        <ShareDialog
          conversationId={shareConversationId}
          open={!!shareConversationId}
          onOpenChange={(open) => {
            if (!open) setShareConversationId(null);
          }}
        />
      )}
    </>
  );
}

interface ConversationSidebarProps {
  embedded?: boolean;
  className?: string;
}

export function ConversationSidebar({ className, embedded = false }: ConversationSidebarProps) {
  const t = useTranslations("chat");
  const [isCollapsed, setIsCollapsed] = useState(false);
  const { isOpen, close } = useChatSidebarStore();
  const {
    conversations,
    currentConversationId,
    isLoading,
    fetchConversations,
    fetchMoreConversations,
    selectConversation,
    deleteConversation,
    archiveConversation,
    unarchiveConversation,
    renameConversation,
    startNewChat,
  } = useConversations();

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  const listProps = {
    conversations,
    currentConversationId,
    isLoading,
    onSelect: selectConversation,
    onDelete: deleteConversation,
    onArchive: archiveConversation,
    onUnarchive: unarchiveConversation,
    onRename: renameConversation,
    onNewChat: startNewChat,
    onLoadMore: fetchMoreConversations,
  };

  const collapsedRail = (
    <div
      className={cn(
        "bg-background hidden w-12 flex-col items-center border-r py-4 md:flex",
        className,
      )}
    >
      <Button
        variant="ghost"
        size="sm"
        className="mb-4 h-10 w-10 p-0"
        onClick={() => setIsCollapsed(false)}
        aria-label={t("expandSidebar")}
      >
        <ChevronRight className="h-4 w-4" aria-hidden />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="h-10 w-10 p-0"
        onClick={startNewChat}
        title={t("newChat")}
        aria-label={t("newChat")}
      >
        <SquarePen className="h-4 w-4" aria-hidden />
      </Button>
    </div>
  );

  return (
    <>
      {isCollapsed ? (
        collapsedRail
      ) : (
        <aside
          className={cn(
            "console-conversation-sidebar hidden w-56 shrink-0 flex-col border-r md:flex",
            embedded && "conversation-sidebar-embedded",
            className,
          )}
        >
          <div className="flex h-12 items-center justify-between border-b px-4 py-3">
            <h2 className="text-sm font-semibold">{t("conversations")}</h2>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              hidden={embedded}
              onClick={() => setIsCollapsed(true)}
              aria-label={t("collapseSidebar")}
            >
              <ChevronLeft className="h-4 w-4" aria-hidden />
            </Button>
          </div>
          <ConversationList {...listProps} />
        </aside>
      )}

      <Sheet
        open={isOpen}
        onOpenChange={(open) => {
          if (!open) close();
        }}
      >
        <SheetContent side="left" className="w-80 p-0">
          <SheetHeader className="h-12 px-4">
            <SheetTitle>{t("conversations")}</SheetTitle>
            <SheetClose onClick={close} />
          </SheetHeader>
          <div className="flex h-[calc(100%-48px)] flex-col">
            <ConversationList {...listProps} onNavigate={close} />
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}

function ViewTab({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
        active
          ? "bg-background text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground",
      )}
    >
      {label}
      <span
        className={cn(
          "text-[10px] tabular-nums",
          active ? "text-foreground" : "text-muted-foreground/60",
        )}
      >
        {count}
      </span>
    </button>
  );
}
