"use client";

import type { GenerationOptions } from "@/lib/model-capabilities";
import dynamic from "next/dynamic";
import { KnowledgeSelector } from "./knowledge-selector";

import { useEffect, useRef, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useChat } from "@/hooks";
import { ChatControls } from "./chat-controls";
import { ChatEmptyState } from "./chat-empty-state";
import { ChatInput } from "./chat-input";
import { FilePreviewPanel } from "./file-preview-panel";
import { SourcesPanel } from "./sources-panel";
import { MessageList } from "./message-list";
import { PendingMessages } from "./pending-messages";
import { ToolApprovalDialog } from "./tool-approval-dialog";
import { QuestionPrompt } from "@/components/ui";
import type { PendingApproval, AskUserQuestion, AskUserAnswer, Decision } from "@/types";
import { useConversationStore } from "@/stores";
import { useConversations } from "@/hooks";
import { useSlashCommands } from "@/hooks";

const ExecutionPanel = dynamic(() => import("./execution-panel").then((m) => m.ExecutionPanel), {
  ssr: false,
});

const SCROLL_NEAR_BOTTOM_THRESHOLD_PX = 150;

export function ChatContainer() {
  const { currentConversationId, isLoading: isConversationLoading } = useConversationStore();
  const { fetchConversations, startNewChat } = useConversations();

  const search = useSearchParams();
  useEffect(() => {
    void fetchConversations();
  }, [fetchConversations, search]);

  const {
    messages,
    updateRating,
    isConnected,
    isProcessing,
    sendMessage,
    stopGeneration,
    queuedMessages,
    cancelQueued,
    retryQueued,
    isSubmitting,
    hasOlder,
    loadOlder,
    loadingOlder,
    connectionError,
    refresh,
    composerKey,
    setPythonEnabled,
    generation,
    generationReady,
    setGeneration,
    pendingApproval,
    sendResumeDecisions,
    pendingQuestions,
    pendingQuestionId,
    answerSubmitting,
    sendAskUserResponses,
  } = useChat({
    conversationId: currentConversationId,
  });

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  // true = user deliberately scrolled up; suppress auto-scroll until they return to bottom
  const userScrolledUpRef = useRef(false);

  // Track whether the user has manually scrolled up so we don't hijack their position
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const handleScroll = () => {
      const distFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      userScrolledUpRef.current = distFromBottom > SCROLL_NEAR_BOTTOM_THRESHOLD_PX;
    };
    container.addEventListener("scroll", handleScroll, { passive: true });
    return () => container.removeEventListener("scroll", handleScroll);
  }, []);

  // Auto-scroll on every messages update unless user has scrolled up
  useEffect(() => {
    if (messages.length === 0 || userScrolledUpRef.current) return;
    messagesEndRef.current?.scrollIntoView({ behavior: "instant" });
  }, [messages]);
  const { commands: slashCommands } = useSlashCommands();

  const handleRegenerate = useCallback(
    (assistantMessageId: string) => {
      const idx = messages.findIndex((m) => m.id === assistantMessageId);
      if (idx < 0) return;
      for (let i = idx - 1; i >= 0; i--) {
        const m = messages[i];
        if (m?.role === "user") {
          sendMessage(m.content, m.fileIds, m.files);
          return;
        }
      }
    },
    [messages, sendMessage],
  );

  // Slash command handlers — passed down to ChatInput so the / palette can
  // run them locally without going through the agent.
  const slashContext = {
    clearChat: startNewChat,
    regenerateLast: () => {
      for (let i = messages.length - 1; i >= 0; i--) {
        const m = messages[i];
        if (m && m.role === "assistant") {
          handleRegenerate(m.id);
          return;
        }
      }
    },
    openSettings: () => {
      document.querySelector<HTMLButtonElement>("[data-chat-settings-trigger]")?.click();
    },
  };

  return (
    <>
      <ChatUI
        onRatingChange={updateRating}
        messages={messages}
        isConnected={isConnected}
        isProcessing={isProcessing}
        isSubmitting={isSubmitting}
        hasOlder={hasOlder}
        onLoadOlder={loadOlder}
        loadingOlder={loadingOlder}
        connectionError={connectionError}
        onRefresh={refresh}
        isLoadingConversation={
          currentConversationId !== null && isConversationLoading && messages.length === 0
        }
        sendMessage={sendMessage}
        composerKey={composerKey}
        onPythonChange={setPythonEnabled}
        generation={generation}
        generationReady={generationReady}
        onGenerationChange={setGeneration}
        onRegenerate={handleRegenerate}
        slashContext={slashContext}
        slashCommands={slashCommands}
        queuedMessages={queuedMessages}
        onCancelQueued={cancelQueued}
        onRetryQueued={retryQueued}
        messagesEndRef={messagesEndRef}
        scrollContainerRef={scrollContainerRef}
        pendingApproval={pendingApproval}
        onResumeDecisions={sendResumeDecisions}
        pendingQuestionId={pendingQuestionId}
        answerSubmitting={answerSubmitting}
        pendingQuestions={pendingQuestions}
        onAnswerQuestions={sendAskUserResponses}
        onCancelRun={stopGeneration}
        onStop={() => stopGeneration()}
      />
      {search.get("run") && <ExecutionPanel />}
    </>
  );
}

interface ChatUIProps {
  messages: import("@/types").ChatMessage[];
  isConnected: boolean;
  isProcessing: boolean;
  isSubmitting?: boolean;
  hasOlder?: boolean;
  onLoadOlder?: () => void;
  loadingOlder?: boolean;
  connectionError?: boolean;
  onRefresh?: () => void;
  /** True while a saved conversation is being loaded — show a skeleton, not empty state. */
  isLoadingConversation?: boolean;
  sendMessage: (
    content: string,
    fileIds?: string[],
    files?: import("@/types").ChatMessageFile[],
  ) => void;
  composerKey?: string;
  generation?: GenerationOptions;
  generationReady?: boolean;
  onGenerationChange?: (value: GenerationOptions) => void;
  onPythonChange?: (value: boolean) => void;
  onModelChange?: (model: string | null) => void;
  onTemperatureChange?: (temperature: number | null) => void;
  onThinkingEffortChange?: (effort: "low" | "medium" | "high" | null) => void;
  onRegenerate?: (messageId: string) => void;
  slashContext?: import("./slash-commands").SlashCommandContext;
  slashCommands?: import("./slash-commands").SlashCommand[];
  queuedMessages?: import("@/hooks/use-chat").QueuedMessage[];
  onCancelQueued?: (id: string) => void;
  onRetryQueued?: (id: string) => void;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  scrollContainerRef: React.RefObject<HTMLDivElement | null>;
  pendingApproval?: PendingApproval | null;
  onResumeDecisions?: (decisions: Decision[]) => void;
  pendingQuestionId?: string;
  answerSubmitting?: boolean;
  pendingQuestions?: AskUserQuestion[] | null;
  onAnswerQuestions?: (answers: AskUserAnswer[]) => void;
  onStop?: () => void;
  onRatingChange?: import("@/lib/chat-turns").ChatRatingUpdate;
  onCancelRun?: (id: string) => void;
}

function ChatUI({
  messages,
  isConnected,
  isProcessing,
  isLoadingConversation,
  isSubmitting,
  hasOlder,
  onLoadOlder,
  loadingOlder,
  connectionError,
  onRefresh,
  sendMessage,
  composerKey,
  generation,
  generationReady,
  onGenerationChange,
  onPythonChange,
  onModelChange,
  onTemperatureChange,
  onThinkingEffortChange,
  onRegenerate,
  slashContext,
  slashCommands,
  queuedMessages,
  onCancelQueued,
  onRetryQueued,
  messagesEndRef,
  scrollContainerRef,
  pendingApproval,
  onResumeDecisions,
  pendingQuestions,
  pendingQuestionId,
  answerSubmitting,
  onAnswerQuestions,
  onStop,
  onCancelRun,
  onRatingChange,
}: ChatUIProps) {
  const tc = useTranslations("common");
  return (
    <div
      className={`quiet-chat flex h-full w-full ${messages.length === 0 && !isLoadingConversation ? "chat-is-empty" : ""}`}
    >
      <div className="mx-auto flex h-full max-w-5xl min-w-0 flex-1 flex-col">
        <div
          ref={scrollContainerRef}
          className="chat-message-scroll flex-1 scrollbar-thin overflow-y-auto px-2 py-4 sm:px-4 sm:py-6"
        >
          {hasOlder && (
            <button
              type="button"
              disabled={loadingOlder}
              onClick={onLoadOlder}
              className="text-muted-foreground mx-auto mb-4 block min-h-10 text-sm underline"
            >
              {loadingOlder ? "正在读取…" : "加载更早的消息"}
            </button>
          )}
          {connectionError && (
            <div role="alert" className="mb-4 rounded-xl border p-3 text-sm">
              暂时无法同步对话，已接收的请求仍由服务器处理。
              <button type="button" onClick={onRefresh} className="text-brand ml-2 underline">
                重新连接
              </button>
            </div>
          )}
          {isLoadingConversation ? (
            <ConversationSkeleton />
          ) : messages.length === 0 ? (
            <div className="flex min-h-full items-center">
              <ChatEmptyState onPick={(prompt) => sendMessage(prompt)} />
            </div>
          ) : (
            <MessageList
              messages={messages}
              onRegenerate={onRegenerate}
              onCancelRun={onCancelRun}
              onRatingChange={onRatingChange}
            />
          )}
          <div ref={messagesEndRef} />
        </div>{" "}
        {pendingApproval && onResumeDecisions && (
          <div className="px-2 pb-2 sm:px-4 sm:pb-2">
            <ToolApprovalDialog
              actionRequests={pendingApproval.actionRequests}
              reviewConfigs={pendingApproval.reviewConfigs}
              onDecisions={onResumeDecisions}
              disabled={!isConnected}
            />
          </div>
        )}
        {pendingQuestions && pendingQuestions.length > 0 && onAnswerQuestions && (
          <div className="px-2 pb-2 sm:px-4 sm:pb-2">
            <QuestionPrompt
              key={pendingQuestionId}
              questions={pendingQuestions}
              disabled={!isConnected || answerSubmitting}
              onComplete={onAnswerQuestions}
            />
          </div>
        )}
        <div className="chat-composer-wrap px-2 pb-2 sm:px-4 sm:pb-4">
          {queuedMessages && queuedMessages.length > 0 && onCancelQueued && (
            <PendingMessages
              messages={queuedMessages}
              onCancel={onCancelQueued}
              onRetry={onRetryQueued}
            />
          )}
          <div className="composer-surface">
            <KnowledgeSelector />
            <ChatInput
              key={composerKey}
              onSend={sendMessage}
              disabled={
                !isConnected ||
                !!isSubmitting ||
                !!pendingApproval ||
                !!(pendingQuestions && pendingQuestions.length)
              }
              isProcessing={isProcessing}
              onStop={onStop}
              slashContext={slashContext}
              commands={slashCommands}
              onPythonChange={onPythonChange}
              controls={
                <ChatControls
                  value={generation}
                  onChange={onGenerationChange}
                  disabled={generationReady === false}
                  onModelChange={onModelChange}
                  onTemperatureChange={onTemperatureChange}
                  onThinkingEffortChange={onThinkingEffortChange}
                />
              }
            />
          </div>
          <p className="text-foreground/40 mt-2 text-center text-[11px]">{tc("aiDisclaimer")}</p>
        </div>
      </div>
      <FilePreviewPanel />
      <SourcesPanel />
    </div>
  );
}

function ConversationSkeleton() {
  // Two faux message bubbles — left (assistant) and right (user) — at the rough
  // proportions a real exchange has, so the layout doesn't pop when messages
  // arrive. Just enough motion to signal "loading", no shimmer chrome.
  return (
    <div className="space-y-6 py-4 sm:py-6">
      <div className="flex gap-2 sm:gap-4">
        <div className="bg-foreground/10 h-8 w-8 shrink-0 animate-pulse rounded-full sm:h-9 sm:w-9" />
        <div className="flex max-w-[85%] flex-1 flex-col gap-2">
          <div className="bg-foreground/10 h-4 w-1/3 animate-pulse rounded-md" />
          <div className="bg-foreground/8 h-4 w-4/5 animate-pulse rounded-md" />
          <div className="bg-foreground/8 h-4 w-2/3 animate-pulse rounded-md" />
        </div>
      </div>
      <div className="flex flex-row-reverse gap-2 sm:gap-4">
        <div className="bg-foreground/10 h-8 w-8 shrink-0 animate-pulse rounded-full sm:h-9 sm:w-9" />
        <div className="flex max-w-[85%] flex-1 flex-col items-end gap-2">
          <div className="bg-foreground/10 h-4 w-1/4 animate-pulse rounded-md" />
          <div className="bg-foreground/8 h-4 w-3/5 animate-pulse rounded-md" />
        </div>
      </div>
      <div className="flex gap-2 sm:gap-4">
        <div className="bg-foreground/10 h-8 w-8 shrink-0 animate-pulse rounded-full sm:h-9 sm:w-9" />
        <div className="flex max-w-[85%] flex-1 flex-col gap-2">
          <div className="bg-foreground/8 h-4 w-3/4 animate-pulse rounded-md" />
          <div className="bg-foreground/8 h-4 w-1/2 animate-pulse rounded-md" />
        </div>
      </div>
    </div>
  );
}
