"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiClient, ApiError } from "@/lib/api-client";
import {
  activeRun,
  lastChatKey,
  type ChatRun,
  type ChatSnapshot,
  type ChatRatingUpdate,
} from "@/lib/chat-turns";
import {
  buildAssistantParts,
  conversationMessageToChatMessage,
  type RawMessage,
} from "@/lib/conversation-to-chat";
import { currentProject } from "@/lib/project-scope";
import { qk } from "@/lib/query-keys";
import { setUrlParam } from "@/lib/utils";
import { useAuthStore, useChatStore, useConversationStore } from "@/stores";
import { useKnowledgeStore } from "@/stores/knowledge-store";
import type { GenerationOptions } from "@/lib/model-capabilities";
import type { AskUserAnswer, ChatMessageFile } from "@/types";

export interface QueuedMessage {
  id: string;
  content: string;
  files?: ChatMessageFile[];
  error?: string;
}
interface Submission extends QueuedMessage {
  payload: Record<string, unknown>;
}
const EMPTY_RUNS: ChatRun[] = [];
interface UseChatOptions {
  conversationId?: string | null;
  onConversationCreated?: (id: string) => void;
}

export function useChat({ conversationId = null, onConversationCreated }: UseChatOptions = {}) {
  const client = useQueryClient();
  const userId = useAuthStore((s) => s.user?.id);
  const projectId = currentProject()?.id;
  const scope = `${userId}:${projectId}:${conversationId}`;
  const scopeRef = useRef(scope);
  scopeRef.current = scope;
  const [online, setOnline] = useState(true);
  const [olderRuns, setOlderRuns] = useState<ChatRun[]>([]);
  const [older, setOlder] = useState<RawMessage[]>([]);
  const [before, setBefore] = useState<string | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [pending, setPending] = useState<Submission[]>([]);
  const [answerSubmitting, setAnswerSubmitting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const sending = useRef(false);
  const python = useRef(false);
  const [generationDraft, setGenerationDraft] = useState<{
    scope: string;
    value: GenerationOptions;
  } | null>(null);
  const generationScope = useRef(scope);
  const composerEpoch = useRef(0);
  if (generationScope.current !== scope) {
    generationScope.current = scope;
    composerEpoch.current += 1;
    python.current = false;
    if (generationDraft !== null) setGenerationDraft(null);
  }
  const historyKey = ["chat-history", userId, projectId, conversationId];
  const runsKey = ["chat-runs", userId, projectId, conversationId];
  const url = `/chat/conversations/${conversationId}/state`;
  const history = useQuery({
    queryKey: historyKey,
    queryFn: ({ signal }) => apiClient.get<ChatSnapshot>(url, { signal }),
    enabled: !!userId && !!conversationId,
    staleTime: 0,
    retry: (count, error) =>
      !(error instanceof ApiError && [401, 403, 404].includes(error.status)) && count < 2,
    refetchOnWindowFocus: true,
  });
  const generation =
    generationDraft?.scope === scope ? generationDraft.value : (history.data?.generation ?? {});
  const generationReady = !conversationId || !!history.data;
  const setGeneration = (value: GenerationOptions) => setGenerationDraft({ scope, value });
  const execution = useQuery({
    queryKey: runsKey,
    queryFn: ({ signal }) =>
      apiClient.get<ChatSnapshot>(`${url}?include_messages=false`, { signal }),
    enabled: !!userId && !!conversationId && !!history.data,
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchInterval: (query) => (query.state.data?.runs.some(activeRun) ? 800 : 15000),
    refetchIntervalInBackground: false,
  });
  const runs =
    (execution.dataUpdatedAt >= history.dataUpdatedAt
      ? execution.data?.runs
      : history.data?.runs) ??
    history.data?.runs ??
    EMPTY_RUNS;
  const active = runs.filter(activeRun);
  const waiting = active.find((r) => r.status === "waiting_input" && r.pending_input);
  const runVersion = runs.map((r) => `${r.id}:${r.status}:${r.attempt}`).join("|");
  const previousVersion = useRef<string | null>(null);

  useEffect(() => {
    setOlder([]);
    setOlderRuns([]);
    setBefore(null);
    setPending([]);
    previousVersion.current = null;
    useChatStore.getState().clearMessages();
    if (userId && conversationId) {
      try {
        localStorage.setItem(lastChatKey(userId, projectId), conversationId);
      } catch {
        /* optional */
      }
    }
  }, [scope, userId, projectId, conversationId]);

  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  useEffect(() => {
    if (history.data && older.length === 0) setBefore(history.data.before ?? null);
  }, [history.data, older.length]);

  useEffect(() => {
    if (previousVersion.current !== null && previousVersion.current !== runVersion) {
      void client.invalidateQueries({
        queryKey: ["chat-history", userId, projectId, conversationId],
      });
      void client.invalidateQueries({ queryKey: qk.conversations.list() });
    }
    previousVersion.current = runVersion;
  }, [runVersion, client, userId, projectId, conversationId]);

  const display = useMemo(() => {
    const byId = new Map(
      [...older, ...(history.data?.messages ?? [])]
        .filter((m) => m.conversation_id === conversationId)
        .map((m) => [m.id, m]),
    );
    return [...byId.values()]
      .sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id))
      .map((raw) => {
        const message = conversationMessageToChatMessage(raw);
        const run =
          runs.find((r) => r.assistant_message_id === raw.id) ??
          olderRuns.find((r) => r.assistant_message_id === raw.id);
        if (!run) return message;
        const content = run.result?.content ?? message.content;
        const thinking = run.result?.thinking ?? message.thinking;
        return {
          ...message,
          content,
          thinking,
          effectiveConfig: run.effective_config,
          isStreaming: run.status === "running",
          parts: buildAssistantParts(message.toolCalls ?? [], content, raw.id, thinking),
          execution: {
            id: run.id,
            status: run.status,
            error: run.error,
            collaborative: run.request.routing?.route === "knowledge_collaboration",
            reason: run.request.routing?.reason,
          },
        };
      });
  }, [older, olderRuns, history.data, runs, conversationId]);

  useEffect(() => {
    useChatStore.setState({ messages: display });
  }, [display]);
  useEffect(() => {
    useConversationStore.getState().setLoading(!!conversationId && history.isPending);
    // A browser tab is only a viewer. Never use this flag to cancel server work.
    useChatStore.getState().setStreaming(active.length > 0);
    return () => useChatStore.getState().setStreaming(false);
  }, [conversationId, history.isPending, active.length]);

  const updateRating: ChatRatingUpdate = (id, rating, counts) => {
    const update = (m: RawMessage) =>
      m.id === id ? { ...m, user_rating: rating, rating_count: counts } : m;
    setOlder((previous) => previous.map(update));
    client.setQueryData<ChatSnapshot>(historyKey, (data) =>
      data ? { ...data, messages: data.messages?.map(update) } : data,
    );
  };

  const refresh = async () => {
    await Promise.all([history.refetch(), execution.refetch()]);
  };
  const loadOlder = async () => {
    if (!before || loadingOlder) return;
    const requestedScope = scope;
    const selection = useConversationStore.getState().selectionVersion;
    setLoadingOlder(true);
    try {
      const data = await apiClient.get<ChatSnapshot>(`${url}?before=${before}`);
      if (
        scopeRef.current !== requestedScope ||
        selection !== useConversationStore.getState().selectionVersion
      )
        return;
      setOlder((previous) => [
        ...(data.messages ?? []),
        ...previous,
        ...(history.data?.messages ?? []),
      ]);
      setOlderRuns((previous) => [...previous, ...data.runs]);
      setBefore(data.before ?? null);
    } catch {
      toast.error("更早的消息加载失败，请重试。");
    } finally {
      setLoadingOlder(false);
    }
  };

  const submit = async (entry: Submission) => {
    if (sending.current) return;
    sending.current = true;
    setSubmitting(true);
    const requestedScope = scope;
    const selection = useConversationStore.getState().selectionVersion;
    try {
      const size = new TextEncoder().encode(JSON.stringify(entry.payload)).length;
      const run = await apiClient.post<ChatRun>("/chat/turns", entry.payload, {
        keepalive: size < 60000,
      });
      if (
        scopeRef.current !== requestedScope ||
        selection !== useConversationStore.getState().selectionVersion ||
        useAuthStore.getState().user?.id !== userId
      )
        return;
      setPending((items) => items.filter((item) => item.id !== entry.id));
      setUrlParam("new", null);
      if (!conversationId) {
        // Assigning a server ID to this draft is the same conversation. Preserve
        // its controls and recording lifecycle; an actual selection change resets them.
        generationScope.current = `${userId}:${projectId}:${run.conversation_id}`;
        setGenerationDraft((draft) =>
          draft?.scope === requestedScope ? { ...draft, scope: generationScope.current } : draft,
        );
        useConversationStore.getState().setCurrentConversationId(run.conversation_id);
        setUrlParam("id", run.conversation_id);
        setUrlParam("knowledge", null);
        setUrlParam("document", null);
        onConversationCreated?.(run.conversation_id);
      }
      await Promise.all([
        client.invalidateQueries({
          queryKey: ["chat-history", userId, projectId, run.conversation_id],
        }),
        client.invalidateQueries({
          queryKey: ["chat-runs", userId, projectId, run.conversation_id],
        }),
        client.invalidateQueries({ queryKey: qk.conversations.list() }),
      ]);
    } catch (error) {
      if (
        scopeRef.current === requestedScope &&
        selection === useConversationStore.getState().selectionVersion
      )
        setPending((items) =>
          items.map((item) =>
            item.id === entry.id
              ? {
                  ...item,
                  error:
                    error instanceof ApiError && error.status < 500
                      ? typeof error.message === "string"
                        ? error.message
                        : "请求未通过校验，请调整后重新发送。"
                      : "发送尚未确认，请点击重试。",
                }
              : item,
          ),
        );
    } finally {
      sending.current = false;
      setSubmitting(false);
    }
  };

  const sendMessage = (content: string, fileIds?: string[], files?: ChatMessageFile[]) => {
    if (sending.current || !userId) return false;
    if (!generationReady) {
      toast.error("请等待本会话设置加载完成后发送。");
      return false;
    }
    const knowledge = useKnowledgeStore.getState();
    if (
      !knowledge.ready ||
      knowledge.busy ||
      knowledge.scopeId !== conversationId ||
      knowledge.error ||
      (knowledge.documentIds !== null && !knowledge.documentsReady)
    ) {
      toast.error(knowledge.error || "请等待知识范围同步完成后发送。");
      return false;
    }
    if (knowledge.ids.length && content.length > 1500) {
      toast.error("知识库问题最多 1500 字。");
      return false;
    }
    if (knowledge.ids.length && knowledge.strict && fileIds?.length) {
      toast.error("请先导入附件，或关闭严格资料模式。");
      return false;
    }
    const id = crypto.randomUUID();
    const entry: Submission = {
      id,
      content,
      files,
      payload: {
        idempotency_key: id,
        conversation_id: conversationId,
        message: content,
        file_ids: fileIds ?? [],
        knowledge_base_ids: knowledge.ids,
        knowledge_document_ids: knowledge.documentIds,
        knowledge_strict: knowledge.strict,
        python_enabled: python.current,
        generation: { ...generation },
      },
    };
    setPending((items) => [...items, entry]);
    void submit(entry);
    return true;
  };
  const retryQueued = (id: string) => {
    const entry = pending.find((item) => item.id === id);
    if (entry) void submit(entry);
  };
  const cancelQueued = (id: string) =>
    setPending((items) => items.filter((item) => item.id !== id));
  const clearQueued = useCallback(() => setPending([]), []);

  const stopGeneration = async (id?: string) => {
    const target = active.find((r) => r.status !== "cancelling" && (!id || r.id === id));
    if (!target) return;
    try {
      await apiClient.post(`/tasks/${target.id}/cancel`, {});
      await refresh();
    } catch {
      toast.error("停止请求未确认，请重试。");
    }
  };
  const sendAskUserResponses = async (answers: AskUserAnswer[]) => {
    const pendingInput = waiting?.pending_input;
    if (!waiting || !pendingInput || answerSubmitting) return;
    setAnswerSubmitting(true);
    let index = 0;
    const mapped = Object.fromEntries(
      pendingInput.calls.map((call) => [
        call.call_id,
        call.questions.map(() => {
          const answer = answers[index++];
          return answer?.skipped ? "用户跳过此问题，请按已有信息继续。" : (answer?.answer ?? "");
        }),
      ]),
    );
    try {
      await apiClient.post(`/tasks/${waiting.id}/resume`, {
        question_id: pendingInput.question_id,
        answers: mapped,
      });
      await refresh();
    } catch {
      toast.error("补充信息未保存，请检查并重试。");
    } finally {
      setAnswerSubmitting(false);
    }
  };
  return {
    messages: display,
    updateRating,
    isConnected: online,
    isProcessing: active.length > 0 || submitting,
    isSubmitting: submitting,
    sendMessage,
    stopGeneration,
    clearMessages: useChatStore.getState().clearMessages,
    queuedMessages: pending,
    retryQueued,
    cancelQueued,
    clearQueued,
    composerKey: `${userId}:${projectId}:${composerEpoch.current}`,
    setPythonEnabled: (value: boolean) => {
      python.current = value;
    },
    generation,
    generationReady,
    setGeneration,
    pendingApproval: null,
    sendResumeDecisions: () => {},
    answerSubmitting,
    pendingQuestionId: waiting ? `${waiting.id}:${waiting.pending_input?.question_id}` : undefined,
    pendingQuestions:
      waiting?.pending_input?.calls.flatMap((call) =>
        call.questions.map((q) => ({
          question: q.question,
          options: q.options ?? [],
          allowCustom: q.allow_custom ?? true,
        })),
      ) ?? null,
    sendAskUserResponses,
    hasOlder: !!before,
    loadOlder,
    loadingOlder,
    connectionError: history.isError || execution.isError,
    refresh,
  };
}
