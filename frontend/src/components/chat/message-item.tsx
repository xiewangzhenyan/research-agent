"use client";

import { useId, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { cn, setUrlParam } from "@/lib/utils";
import type { ChatMessage, ChatMessageFile, MessagePart } from "@/types";
import { ResearchMark } from "@/components/brand/research-mark";
import { toolCallsOf } from "@/lib/run-summary";
import { RoleStrip } from "./role-strip";
import { ToolCallCard } from "./tool-call-card";
import { MarkdownContent } from "./markdown-content";
import { RememberMessage } from "@/components/memory/memory-editor";
import { ContextUsage } from "./context-usage";
import { MemoryUsageBadge } from "@/components/memory/memory-usage";
import { useProject } from "@/components/projects/project-provider";
import { CopyButton } from "./copy-button";
import { ExportAnswer } from "./export-answer";
import { MessageArtifacts } from "./message-artifacts";
import { RatingButtons } from "./rating-buttons";
import { useChatStore, useFilePreviewStore } from "@/stores";
import { useSourcesPanelStore } from "@/stores/sources-panel-store";
import {
  ChevronRight,
  Clock3,
  FileText,
  Globe,
  ListTree,
  Loader2,
  Paperclip,
  RefreshCw,
  User,
  Wrench,
} from "lucide-react";
import Image from "next/image";
import { useAuthStore } from "@/stores";
import { getFileUrl } from "@/lib/file-api";
import { extractSources } from "@/lib/chat-sources";
import type { SourceItem } from "@/lib/chat-sources";

function ThinkingBlock({
  text,
  isStreaming,
}: {
  text: string;
  open?: boolean;
  isStreaming: boolean;
}) {
  const zh = useLocale() === "zh";
  const [expanded, setExpanded] = useState(false);
  const id = useId();
  return (
    <div className="text-muted-foreground py-1 text-xs">
      <button
        type="button"
        className="hover:text-foreground flex min-h-8 items-center gap-2"
        aria-expanded={expanded}
        aria-controls={id}
        onClick={() => setExpanded(!expanded)}
      >
        <ChevronRight
          className={cn(
            "h-3.5 w-3.5 transition-transform motion-reduce:transition-none",
            expanded && "rotate-90",
          )}
        />
        {isStreaming ? (zh ? "正在思考" : "Thinking") : zh ? "思考摘要" : "Reasoning summary"}
      </button>
      <div id={id} className="chat-reasoning-content" data-open={expanded} aria-hidden={!expanded}>
        <div>
          <pre className="font-sans text-xs leading-6 whitespace-pre-wrap">{text}</pre>
        </div>
      </div>
    </div>
  );
}

function TextBubble({
  text,
  showCursor,
  isUser,
  onCiteClick,
}: {
  text: string;
  showCursor: boolean;
  isUser: boolean;
  onCiteClick?: (index: number) => void;
}) {
  return (
    <div
      className={cn(
        "relative min-w-0",
        isUser
          ? "bg-card text-foreground rounded-xl rounded-tr-none border px-4 py-2.5 shadow-[var(--shadow-panel)]"
          : "py-1",
      )}
    >
      {isUser ? (
        <p className="text-sm break-words whitespace-pre-wrap">{text}</p>
      ) : (
        <div className="chat-answer max-w-none">
          <MarkdownContent content={text} onCiteClick={onCiteClick} isStreaming={showCursor} />
          {showCursor && <span className="answer-caret ml-1" aria-hidden />}
        </div>
      )}
    </div>
  );
}

function SourcesButton({ sources, onClick }: { sources: SourceItem[]; onClick: () => void }) {
  const zh = useLocale() === "zh";
  const ragCount = sources.filter((s) => s.type === "rag").length;
  const webCount = sources.filter((s) => s.type === "web").length;

  return (
    <button
      type="button"
      onClick={onClick}
      className="bg-card hover:border-brand/40 hover:bg-brand/5 inline-flex items-center gap-1.5 rounded-sm border px-2.5 py-1 transition-colors"
    >
      <span className="flex -space-x-1">
        {ragCount > 0 && (
          <span className="bg-muted border-background inline-flex h-4 w-4 items-center justify-center rounded-sm border">
            <FileText className="text-foreground/60 h-2.5 w-2.5" />
          </span>
        )}
        {webCount > 0 && (
          <span className="bg-muted border-background inline-flex h-4 w-4 items-center justify-center rounded-sm border">
            <Globe className="text-foreground/60 h-2.5 w-2.5" />
          </span>
        )}
      </span>
      <span className="text-foreground/70 text-2xs font-medium">
        {zh
          ? `${sources.length} 条原文依据`
          : `${sources.length} source${sources.length !== 1 ? "s" : ""}`}
      </span>
    </button>
  );
}

/** Consecutive tool parts share one trace so their rows connect into a timeline. */
function groupParts(parts: MessagePart[]): (MessagePart | MessagePart[])[] {
  const out: (MessagePart | MessagePart[])[] = [];
  for (const part of parts) {
    const last = out[out.length - 1];
    if (part.type === "tool" && part.toolCall) {
      if (Array.isArray(last)) last.push(part);
      else out.push([part]);
    } else {
      out.push(part);
    }
  }
  return out;
}

const RUN_STATUS_ICON: Record<string, typeof Clock3> = {
  queued: Clock3,
  running: Loader2,
  waiting_input: Clock3,
  cancelling: Loader2,
};

interface MessageItemProps {
  message: ChatMessage;
  groupPosition?: "first" | "middle" | "last" | "single";
  onRatingChange?: import("@/lib/chat-turns").ChatRatingUpdate;
  onCancel?: () => void;
  onRegenerate?: () => void;
}

export function MessageItem({
  message,
  groupPosition,
  onRegenerate,
  onCancel,
  onRatingChange,
}: MessageItemProps) {
  const zh = useLocale() === "zh";
  const t = useTranslations("chat.agents");
  const workspace = useProject();
  const isUser = message.role === "user";
  const updateMessage = useChatStore((state) => state.updateMessage);
  const openPreview = useFilePreviewStore((s) => s.open);
  const openSources = useSourcesPanelStore((s) => s.open);
  const { user: authUser, avatarVersion } = useAuthStore();
  const isGrouped = groupPosition && groupPosition !== "single";

  const sources = !isUser ? extractSources(message) : [];
  const hasSources = sources.length > 0 && !message.isStreaming;
  const onCiteClick = hasSources ? (index: number) => openSources(sources, index) : undefined;
  const toolCount = !isUser && !message.isStreaming ? toolCallsOf(message).length : 0;
  const runActive =
    !!message.execution &&
    ["queued", "running", "waiting_input", "cancelling"].includes(message.execution.status);

  return (
    <div
      className={cn(
        "group relative flex gap-2 overflow-visible sm:gap-4",
        isGrouped ? "py-2 sm:py-3" : "py-3 sm:py-4",
        isUser && "flex-row-reverse",
      )}
    >
      {" "}
      {isGrouped && !isUser && (
        <div
          className="bg-border absolute left-[15px] w-0.5 sm:left-[17px]"
          style={
            groupPosition === "first"
              ? { top: "24px", bottom: "0" }
              : groupPosition === "last"
                ? { top: "0", height: "24px" }
                : { top: "0", bottom: "0" }
          }
        />
      )}
      <div
        className={cn(
          "z-10 flex h-8 w-8 flex-shrink-0 items-center justify-center overflow-hidden sm:h-9 sm:w-9",
          isUser ? "bg-brand/15 text-brand border-brand/30 rounded-sm border" : "rounded-sm",
          isGrouped && !isUser && "ring-background ring-2",
        )}
      >
        {isUser && authUser?.avatar_url ? (
          <Image
            src={`/api/users/avatar/${authUser.id}?v=${avatarVersion}`}
            alt=""
            width={36}
            height={36}
            className="h-full w-full object-cover"
            unoptimized
          />
        ) : isUser ? (
          <User className="h-4 w-4" />
        ) : (
          <ResearchMark size={36} animated={runActive} className="h-full w-full" />
        )}
      </div>
      <div
        className={cn(
          "min-w-0 flex-1 space-y-2",
          isUser ? "max-w-[85%]" : "max-w-full",
          isUser && "flex flex-col items-end",
        )}
      >
        {isUser &&
          (() => {
            const attachments: AttachmentDisplay[] =
              message.files && message.files.length > 0
                ? message.files.map((f) => ({ kind: kindFor(f), file: f }))
                : (message.fileIds ?? []).map((id) => ({ kind: "unknown" as const, id }));
            if (attachments.length === 0) return null;
            return (
              <div className="flex flex-wrap gap-2">
                {attachments.map((att) =>
                  att.kind === "image" ? (
                    <button
                      type="button"
                      key={att.file.id}
                      onClick={() => openPreview(att.file)}
                      className="hover:ring-foreground/30 block overflow-hidden rounded-xl border ring-2 ring-transparent transition-shadow"
                      title={`Open ${att.file.filename}`}
                    >
                      <Image
                        src={getFileUrl(att.file.id)}
                        alt={att.file.filename}
                        width={320}
                        height={256}
                        className="h-auto max-h-64 w-auto max-w-xs object-contain"
                        unoptimized
                      />
                    </button>
                  ) : "file" in att ? (
                    <FileChip
                      key={att.file.id}
                      filename={att.file.filename}
                      hint={att.file.mime_type}
                      onClick={() => openPreview(att.file)}
                    />
                  ) : (
                    <FileChip key={att.id} filename="Attached file" href={getFileUrl(att.id)} />
                  ),
                )}
              </div>
            );
          })()}

        {(() => {
          const rawParts = message.parts ?? [];
          const parts = rawParts;
          const useParts = !isUser && parts.length > 0;

          // "Thinking…" placeholder — shown until anything streams in.
          const showPlaceholder =
            !isUser &&
            message.isStreaming &&
            !message.content &&
            parts.length === 0 &&
            (!message.toolCalls || message.toolCalls.length === 0);

          return (
            <>
              {!isUser && message.execution && message.execution.status !== "completed" && (
                <div
                  role="status"
                  className={cn(
                    "panel-inset relative mb-2 flex flex-wrap items-center gap-x-2 overflow-hidden px-3 py-2 text-xs leading-6",
                    message.execution.status === "failed"
                      ? "text-destructive"
                      : "text-muted-foreground",
                  )}
                >
                  {(() => {
                    const Icon = RUN_STATUS_ICON[message.execution.status];
                    return Icon ? (
                      <Icon
                        aria-hidden
                        className={cn("text-brand h-3.5 w-3.5", Icon === Loader2 && "animate-spin")}
                      />
                    ) : null;
                  })()}
                  {
                    (
                      {
                        queued: "消息已保存，正在排队",
                        running: "正在处理，离开页面后会继续",
                        waiting_input: "等待补充信息，回答后继续",
                        cancelling: "正在停止",
                        cancelled: "已停止，已生成内容保留",
                        failed: "处理失败，已生成内容保留",
                      } as Record<string, string>
                    )[message.execution.status]
                  }
                  {message.execution.error && <p className="w-full">{message.execution.error}</p>}
                  {onCancel &&
                    ["queued", "running", "waiting_input"].includes(message.execution.status) && (
                      <button
                        type="button"
                        onClick={onCancel}
                        className="hover:text-foreground ml-auto rounded-md px-1.5 underline-offset-4 hover:underline"
                      >
                        停止此条
                      </button>
                    )}
                  {["queued", "running"].includes(message.execution.status) && (
                    <span aria-hidden className="step-progress absolute inset-x-0 bottom-0 h-px" />
                  )}
                </div>
              )}
              {!isUser && message.execution && (
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  {message.execution.collaborative && (
                    <span title={message.execution.reason}>
                      <RoleStrip
                        running={runActive}
                        label={runActive ? t("running") : t("strip")}
                      />
                    </span>
                  )}
                  <button
                    type="button"
                    aria-haspopup="dialog"
                    onClick={() => setUrlParam("run", message.execution!.id)}
                    className="text-muted-foreground hover:text-foreground hover:border-border-strong bg-card inline-flex min-h-8 items-center gap-1.5 rounded-sm border px-3 text-xs transition-colors"
                  >
                    <ListTree aria-hidden className="h-3.5 w-3.5" />
                    {zh ? "执行详情与文件" : "Execution details and files"}
                  </button>
                </div>
              )}
              {showPlaceholder && (
                <div className="flex items-center gap-2 py-2.5" role="status" aria-live="polite">
                  <div className="flex gap-1" aria-hidden="true">
                    <span className="bg-role-plan h-1.5 w-1.5 animate-bounce rounded-sm [animation-delay:0ms]" />
                    <span className="bg-role-research h-1.5 w-1.5 animate-bounce rounded-sm [animation-delay:150ms]" />
                    <span className="bg-role-write h-1.5 w-1.5 animate-bounce rounded-sm [animation-delay:300ms]" />
                  </div>
                  <span className="text-muted-foreground text-xs">
                    {zh ? "正在思考…" : "Thinking…"}
                  </span>
                </div>
              )}

              {useParts ? (
                /* Ordered timeline: render each part in arrival order; runs of tool
                   calls are drawn as one connected trace. */
                groupParts(parts).map((entry) => {
                  if (Array.isArray(entry)) {
                    return (
                      <div key={entry[0]!.id} className="trace w-full py-1">
                        {entry.map((part) => (
                          <ToolCallCard key={part.id} toolCall={part.toolCall!} />
                        ))}
                      </div>
                    );
                  }
                  const part = entry;
                  const i = parts.indexOf(part);
                  if (part.type === "thinking" && part.content) {
                    return (
                      <ThinkingBlock
                        key={part.id}
                        text={part.content}
                        open={Boolean(message.isStreaming) && i === parts.length - 1}
                        isStreaming={Boolean(message.isStreaming)}
                      />
                    );
                  }
                  if (part.type === "text" && part.content) {
                    return (
                      <TextBubble
                        key={part.id}
                        text={part.content}
                        showCursor={Boolean(message.isStreaming) && i === parts.length - 1}
                        isUser={isUser}
                        onCiteClick={onCiteClick}
                      />
                    );
                  }
                  return null;
                })
              ) : (
                /* Legacy fallback: user / pre-parts messages. */
                <>
                  {!isUser && message.thinking && (
                    <ThinkingBlock
                      text={message.thinking}
                      open={Boolean(message.isStreaming)}
                      isStreaming={Boolean(message.isStreaming)}
                    />
                  )}
                  {message.content && (
                    <TextBubble
                      text={message.content}
                      showCursor={!isUser && Boolean(message.isStreaming)}
                      isUser={isUser}
                      onCiteClick={onCiteClick}
                    />
                  )}
                  {message.toolCalls && message.toolCalls.length > 0 && (
                    <div className="trace w-full py-1">
                      {message.toolCalls.map((toolCall) => (
                        <ToolCallCard key={toolCall.id} toolCall={toolCall} />
                      ))}
                    </div>
                  )}
                </>
              )}
            </>
          );
        })()}

        {!isUser && workspace && <MessageArtifacts message={message} />}

        {!isUser && message.effectiveConfig && !message.isStreaming && (
          <details className="text-muted-foreground mt-2 text-xs">
            <summary className="min-h-8 cursor-pointer py-2">
              {zh ? "本次回答配置" : "Answer configuration"}
            </summary>
            <dl className="border-border bg-card mt-1 space-y-2 rounded-xl border p-3">
              <div>
                <dt>{zh ? "模型" : "Model"}</dt>
                <dd className="text-foreground font-mono break-all">
                  {message.effectiveConfig.model}
                </dd>
              </div>
              <div>
                <dt>{zh ? "温度" : "Temperature"}</dt>
                <dd>{message.effectiveConfig.temperature ?? (zh ? "未发送该参数" : "Not sent")}</dd>
              </div>
              <div>
                <dt>Top P</dt>
                <dd>{message.effectiveConfig.top_p ?? (zh ? "未发送该参数" : "Not sent")}</dd>
              </div>
              <div>
                <dt>{zh ? "输出长度上限" : "Output token limit"}</dt>
                <dd>
                  {message.effectiveConfig.max_output_tokens ?? (zh ? "未记录" : "Not recorded")}
                </dd>
              </div>
              <div>
                <dt>{zh ? "推理强度" : "Reasoning effort"}</dt>
                <dd>
                  {message.effectiveConfig.thinking_effort
                    ? zh
                      ? { low: "低", medium: "中", high: "高" }[
                          message.effectiveConfig.thinking_effort
                        ]
                      : message.effectiveConfig.thinking_effort
                    : zh
                      ? "由模型服务决定"
                      : "Provider default"}
                </dd>
              </div>
              <div>
                <dt>{zh ? "配置策略版本" : "Policy version"}</dt>
                <dd className="font-mono break-all">{message.effectiveConfig.policy_version}</dd>
              </div>
            </dl>
          </details>
        )}

        {!isUser && !message.isStreaming && workspace && (
          <>
            <MemoryUsageBadge usage={message.effectiveConfig?.memory} />
            <ContextUsage
              usage={message.effectiveConfig?.context}
              conversationId={message.conversationId}
              answerId={message.id}
            />
          </>
        )}

        {!isUser && (hasSources || toolCount > 0) && (
          <div className="mt-1 flex flex-wrap items-center gap-2">
            {toolCount > 0 && (
              <span className="text-muted-foreground text-2xs inline-flex items-center gap-1.5">
                <Wrench aria-hidden className="h-3 w-3" />
                {t("toolCount", { count: toolCount })}
              </span>
            )}
            {hasSources && (
              <SourcesButton sources={sources} onClick={() => openSources(sources, null)} />
            )}
          </div>
        )}

        {!message.isStreaming && message.content && (
          <div
            className={cn(
              "flex items-center gap-2 transition-opacity",
              isUser && "flex-row-reverse",
              !onRegenerate &&
                "group-hover:opacity-100 focus-within:opacity-100 [@media(hover:hover)]:opacity-0",
            )}
          >
            {message.timestamp && (
              <span className="text-muted-foreground text-2xs tabular-nums">
                {new Date(message.timestamp).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            )}
            <CopyButton
              text={message.content}
              className={cn(
                "h-6 w-6 rounded-md focus-visible:opacity-100 sm:opacity-60 sm:group-hover:opacity-100",
                isUser ? "bg-secondary hover:bg-secondary/80" : "bg-muted hover:bg-muted/80",
              )}
            />
            {workspace && authUser && <RememberMessage message={message} />}
            {!isUser && (
              <ExportAnswer
                content={message.content}
                messageId={message.id}
                saved={
                  !!workspace &&
                  !message.isTemporaryId &&
                  (!message.execution || message.execution.status === "completed")
                }
              />
            )}
            {!isUser && onRegenerate && (
              <button
                type="button"
                onClick={onRegenerate}
                title={zh ? "重新生成" : "Regenerate response"}
                aria-label={zh ? "重新生成" : "Regenerate response"}
                className="bg-muted hover:bg-muted/80 text-foreground/70 hover:text-foreground inline-flex h-6 w-6 items-center justify-center rounded-md transition-colors focus-visible:opacity-100 sm:opacity-60 sm:group-hover:opacity-100"
              >
                <RefreshCw className="h-3 w-3" />
              </button>
            )}
            {!isUser && (
              <RatingButtons
                messageId={message.id}
                conversationId={message.conversationId ?? ""}
                currentRating={message.user_rating ?? null}
                ratingCount={message.rating_count ?? undefined}
                isAssistant={!isUser}
                onRatingChange={(updatedData) => {
                  onRatingChange?.(message.id, updatedData.rating, updatedData.rating_count);
                  updateMessage(message.id, (msg) => ({
                    ...msg,
                    user_rating: updatedData.rating,
                    rating_count: updatedData.rating_count,
                  }));
                }}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

type AttachmentDisplay =
  | { kind: "image"; file: ChatMessageFile }
  | { kind: "file"; file: ChatMessageFile }
  | { kind: "unknown"; id: string };

function kindFor(file: ChatMessageFile): "image" | "file" {
  if (file.file_type === "image") return "image";
  if (file.mime_type.startsWith("image/")) return "image";
  return "file";
}

function FileChip({
  filename,
  hint,
  onClick,
  href,
}: {
  filename: string;
  hint?: string;
  /** When provided, clicking opens the file in the preview panel. */
  onClick?: () => void;
  /** Fallback for legacy attachments without full metadata — opens in new tab. */
  href?: string;
}) {
  const ext = filename.includes(".") ? filename.split(".").pop()!.toLowerCase() : null;
  const className =
    "border-foreground/15 bg-card hover:border-foreground/40 inline-flex max-w-xs items-center gap-2 rounded-xl border px-3 py-2 transition-colors text-left";
  const inner = (
    <>
      <span className="bg-foreground/8 text-foreground/65 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg">
        <FileText className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="text-foreground block truncate text-sm font-medium">{filename}</span>
        {ext && (
          <span className="text-foreground/55 font-mono text-[10px] tracking-wider uppercase">
            {ext}
          </span>
        )}
      </span>
      <Paperclip className="text-foreground/40 h-3.5 w-3.5 shrink-0" />
    </>
  );
  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={className} title={hint ?? filename}>
        {inner}
      </button>
    );
  }
  return (
    <a
      href={href ?? "#"}
      target="_blank"
      rel="noopener noreferrer"
      className={className}
      title={hint ?? filename}
    >
      {inner}
    </a>
  );
}
