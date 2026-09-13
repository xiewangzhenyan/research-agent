"use client";

import { useLocale } from "next-intl";
import { useKnowledgeStore } from "@/stores/knowledge-store";
import { lastChatKey } from "@/lib/chat-turns";
import { currentProject } from "@/lib/project-scope";
import { useCallback, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";
import { qk } from "@/lib/query-keys";
import { getErrorMessage, setUrlParam } from "@/lib/utils";
import { useConversationStore, useChatStore, useAuthStore } from "@/stores";
import type { Conversation, ConversationListResponse } from "@/types";

interface CreateConversationResponse {
  id: string;
  title?: string;
  created_at: string;
  updated_at: string;
  is_archived: boolean;
  is_demo?: boolean;
}

const PAGE_SIZE = 30;

export function useConversations() {
  const zh = useLocale() === "zh";
  const queryClient = useQueryClient();
  const {
    currentConversationId,
    currentMessages,
    isLoading: selectLoading,
    error,
    setCurrentConversationId,
    setCurrentMessages,
    setLoading,
    setError,
  } = useConversationStore();
  const { clearMessages } = useChatStore();
  const hasMoreRef = useRef(true);
  // React Query owns the list: cached across navigations, deduped, no refetch
  // storms (this replaces the old manual fetch + session-singleton guard).
  // Both active and archived are fetched in one call so the sidebar tabs can
  // partition them client-side. Mutations patch the cache directly.
  const { data: conversations = [], isLoading: listLoading } = useQuery({
    queryKey: qk.conversations.list(),
    queryFn: async () => {
      const response = await apiClient.get<ConversationListResponse>(
        `/conversations?limit=${PAGE_SIZE}&include_archived=true`,
      );
      hasMoreRef.current = response.items.length >= PAGE_SIZE;
      return response.items;
    },
  });

  // `isLoading` historically reflected both the list fetch and the
  // select-messages fetch; preserve that union.
  const isLoading = listLoading || selectLoading;

  const writeCache = useCallback(
    (updater: (prev: Conversation[]) => Conversation[]) =>
      queryClient.setQueryData<Conversation[]>(qk.conversations.list(), (prev = []) =>
        updater(prev),
      ),
    [queryClient],
  );

  // Selection is immediate; the chat hook loads history independently of the list.
  const fetchConversations = useCallback(async () => {
    const params = new URLSearchParams(window.location.search);
    const userId = useAuthStore.getState().user?.id;
    let id = params.get("id");
    if (
      !id &&
      !params.has("new") &&
      !params.has("knowledge") &&
      !params.has("document") &&
      !params.has("run") &&
      userId
    ) {
      try {
        id = localStorage.getItem(lastChatKey(userId, currentProject()?.id));
      } catch {
        /* optional */
      }
    }
    if (params.has("new")) id = null;
    if (id !== useConversationStore.getState().currentConversationId) {
      setCurrentConversationId(id);
      clearMessages();
      setCurrentMessages([]);
      setUrlParam("id", id);
    }
  }, [setCurrentConversationId, setCurrentMessages, clearMessages]);

  const loadingMoreRef = useRef(false);

  const fetchMoreConversations = useCallback(async () => {
    if (!hasMoreRef.current || loadingMoreRef.current) return;
    loadingMoreRef.current = true;
    const current = queryClient.getQueryData<Conversation[]>(qk.conversations.list()) ?? [];
    try {
      const response = await apiClient.get<ConversationListResponse>(
        `/conversations?limit=${PAGE_SIZE}&skip=${current.length}&include_archived=true`,
      );
      if (response.items.length > 0) {
        // Dedupe in case a refetch raced with the append.
        writeCache((prev) => {
          const seen = new Set(prev.map((c) => c.id));
          return [...prev, ...response.items.filter((c) => !seen.has(c.id))];
        });
      }
      hasMoreRef.current = response.items.length >= PAGE_SIZE;
    } catch {
    } finally {
      loadingMoreRef.current = false;
    }
  }, [queryClient, writeCache]);

  const createConversation = useCallback(
    async (title?: string): Promise<Conversation | null> => {
      setLoading(true);
      setError(null);
      try {
        const response = await apiClient.post<CreateConversationResponse>("/conversations", {
          title,
        });
        const newConversation: Conversation = {
          id: response.id,
          title: response.title,
          created_at: response.created_at,
          updated_at: response.updated_at,
          is_archived: response.is_archived,
          is_demo: response.is_demo ?? false,
        };
        writeCache((prev) => [newConversation, ...prev]);
        return newConversation;
      } catch (err) {
        const message = getErrorMessage(err, "Failed to create conversation");
        setError(message);
        return null;
      } finally {
        setLoading(false);
      }
    },
    [writeCache, setLoading, setError],
  );

  const selectConversation = useCallback(
    async (id: string) => {
      setCurrentConversationId(id);
      clearMessages();
      setCurrentMessages([]);
      setError(null);
      setUrlParam("id", id);
      setUrlParam("new", null);
      setUrlParam("run", null);
    },
    [setCurrentConversationId, clearMessages, setCurrentMessages, setError],
  );

  const archiveConversation = useCallback(
    async (id: string) => {
      try {
        await apiClient.patch(`/conversations/${id}`, { is_archived: true });
        writeCache((prev) => prev.map((c) => (c.id === id ? { ...c, is_archived: true } : c)));
        toast.success(zh ? "会话已归档" : "Conversation archived");
      } catch (err) {
        const message = getErrorMessage(
          err,
          zh ? "归档会话失败" : "Failed to archive conversation",
        );
        setError(message);
        toast.error(message);
      }
    },
    [writeCache, setError, zh],
  );

  const unarchiveConversation = useCallback(
    async (id: string) => {
      try {
        await apiClient.patch(`/conversations/${id}`, { is_archived: false });
        writeCache((prev) => prev.map((c) => (c.id === id ? { ...c, is_archived: false } : c)));
        toast.success(zh ? "会话已恢复" : "Conversation restored");
      } catch (err) {
        const message = getErrorMessage(
          err,
          zh ? "恢复会话失败" : "Failed to restore conversation",
        );
        setError(message);
        toast.error(message);
      }
    },
    [writeCache, setError, zh],
  );

  const deleteConversation = useCallback(
    async (id: string) => {
      try {
        await apiClient.delete(`/conversations/${id}`);
        writeCache((prev) => prev.filter((c) => c.id !== id));
        // Mirror the old store behavior: clear the active selection if it was
        // the conversation we just removed.
        if (useConversationStore.getState().currentConversationId === id) {
          setCurrentConversationId(null);
          setUrlParam("new", "1");
          setUrlParam("run", null);
          clearMessages();
          setCurrentMessages([]);
          setUrlParam("id", null);
        }
        toast.success(zh ? "会话已删除" : "Conversation deleted");
        return true;
      } catch (err) {
        const message = getErrorMessage(err, zh ? "删除会话失败" : "Failed to delete conversation");
        setError(message);
        toast.error(message);
        return false;
      }
    },
    [writeCache, setCurrentConversationId, setCurrentMessages, clearMessages, setError, zh],
  );

  const renameConversation = useCallback(
    async (id: string, title: string) => {
      try {
        await apiClient.patch(`/conversations/${id}`, { title });
        writeCache((prev) => prev.map((c) => (c.id === id ? { ...c, title } : c)));
        toast.success(zh ? "会话名称已保存" : "Conversation renamed");
        return true;
      } catch (err) {
        const message = getErrorMessage(
          err,
          zh ? "保存会话名称失败" : "Failed to rename conversation",
        );
        setError(message);
        toast.error(message);
        return false;
      }
    },
    [writeCache, setError, zh],
  );
  const updateActiveKBs = useCallback(
    async (conversationId: string, kbIds: string[]) => {
      writeCache((prev) =>
        prev.map((c) => (c.id === conversationId ? { ...c, active_knowledge_base_ids: kbIds } : c)),
      );
      try {
        await apiClient.patch(`/conversations/${conversationId}`, {
          active_knowledge_base_ids: kbIds,
        });
      } catch {
        toast.error("Failed to update knowledge bases");
      }
    },
    [writeCache],
  );

  const startNewChat = useCallback(async () => {
    clearMessages();
    setCurrentMessages([]);
    setCurrentConversationId(null);
    const userId = useAuthStore.getState().user?.id;
    if (userId) {
      try {
        localStorage.removeItem(lastChatKey(userId, currentProject()?.id));
      } catch {
        /* optional */
      }
    }
    setUrlParam("new", "1");
    setUrlParam("run", null);
    setUrlParam("id", null);
    setUrlParam("knowledge", null);
    setUrlParam("document", null);
    useKnowledgeStore.setState({
      ids: [...(currentProject()?.knowledge_base_ids ?? [])],
      documentIds: null,
      strict: true,
      scopeId: null,
      ready: true,
      documentsReady: false,
      busy: false,
      error: null,
    });
  }, [clearMessages, setCurrentMessages, setCurrentConversationId]);

  return {
    conversations,
    currentConversationId,
    currentMessages,
    isLoading,
    error,
    fetchConversations,
    fetchMoreConversations,
    hasMore: hasMoreRef.current,
    createConversation,
    selectConversation,
    archiveConversation,
    unarchiveConversation,
    deleteConversation,
    renameConversation,
    startNewChat,
    updateActiveKBs,
  };
}
