"use client";
import { useLocale } from "next-intl";
import { useState, type MouseEvent } from "react";
import { Card, CardContent, Button } from "@/components/ui";
import type { ToolCall } from "@/types";
import {
  Wrench,
  Clock,
  Search,
  Globe,
  ChevronDown,
  ChevronUp,
  Code2,
  MessageCircleQuestion,
  Loader2,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toolCaption, toolDisplayName } from "@/lib/agent-step-captions";
import { DateTimeResult } from "./tool-results/datetime";
import { RAGSearchResults } from "./tool-results/rag";
import { WebSearchResults, parseWebSearch } from "./tool-results/web-search";
import { AskUserResult } from "./tool-results/ask-user";
import { GenericToolResult, RawToolView } from "./tool-results/generic";

interface ToolCallCardProps {
  toolCall: ToolCall;
  /** Force the card open on mount (used by the demo "Agent's computer" panel). */
  defaultExpanded?: boolean;
}

export function ToolCallCard({ toolCall, defaultExpanded = false }: ToolCallCardProps) {
  const zh = useLocale() === "zh";
  // Collapsed by default — the bar acts as the toggle. `showRaw` swaps the
  // formatted view for args + raw output (the </> button). Charts are the
  // exception: they're only useful when visible, so expand them by default.
  const [expanded, setExpanded] = useState(
    defaultExpanded || toolCall.name === "ask_user" || false,
  );
  const [showRaw, setShowRaw] = useState(false);

  // Short input hint shown in the collapsed bar — the query for search
  // tools, the URL for fetch_url, etc. (any tool with a url/query arg).
  const urlArg = toolCall.args?.url;
  const queryArg = toolCall.args?.query;
  const inputHint =
    typeof urlArg === "string" ? urlArg : typeof queryArg === "string" ? queryArg : null;

  const resultText =
    toolCall.result !== undefined
      ? typeof toolCall.result === "string"
        ? toolCall.result
        : JSON.stringify(toolCall.result, null, 2)
      : "";

  const isDateTime = toolCall.name === "get_current_datetime" && toolCall.status === "completed";
  const isRAGSearch =
    (toolCall.name === "search_knowledge_base" || toolCall.name === "search_documents") &&
    toolCall.status === "completed" &&
    typeof toolCall.result === "string";
  const webResults =
    (toolCall.name === "web_search_tool" || toolCall.name === "search_web") &&
    toolCall.status === "completed" &&
    typeof toolCall.result === "string"
      ? parseWebSearch(toolCall.result)
      : null;
  const isWebSearch = webResults !== null;
  const isAskUser = toolCall.name === "ask_user";

  const hasSpecialRenderer = isDateTime || isRAGSearch || isWebSearch || isAskUser;
  const friendlyName = isDateTime
    ? zh
      ? "当前日期与时间"
      : "Current Date & Time"
    : isRAGSearch
      ? zh
        ? "知识库检索"
        : "Knowledge Base Search"
      : isWebSearch
        ? zh
          ? "联网搜索"
          : "Web Search"
        : isAskUser
          ? zh
            ? "补充提问"
            : "Question"
          : toolCall.name === "run_python"
            ? zh
              ? "运行 Python"
              : "Run Python"
            : toolCall.name === "create_document"
              ? zh
                ? "生成文档"
                : "Create document"
              : toolDisplayName(toolCall.name);

  const ToolIcon = isDateTime
    ? Clock
    : isRAGSearch
      ? Search
      : isWebSearch
        ? Globe
        : isAskUser
          ? MessageCircleQuestion
          : Wrench;

  const toggleExpanded = () => {
    setExpanded((prev) => {
      const next = !prev;
      if (!next) setShowRaw(false);
      return next;
    });
  };

  const toggleRaw = (e: MouseEvent) => {
    e.stopPropagation();
    setShowRaw((r) => !r);
    setExpanded(true);
  };

  // While still running: narrate what the agent is doing instead of the finished label,
  // and swap the chevron/raw toggle for a spinner — the header becomes a step caption.
  const isRunning = toolCall.status === "running" || toolCall.status === "pending";
  const isError = toolCall.status === "error";
  const liveCaption =
    toolCall.name === "create_document" && zh ? "正在生成文档" : toolCaption(toolCall.name);

  return (
    <Card
      className={cn(
        "bg-muted/50 step-card-in",
        isRunning && "border-brand/50 relative overflow-hidden",
      )}
    >
      <div
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        onClick={toggleExpanded}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggleExpanded();
          }
        }}
        className="hover:bg-foreground/[0.03] flex w-full cursor-pointer items-center justify-between gap-2 px-3 py-2 text-left transition-colors"
      >
        <div className="flex min-w-0 items-center gap-2">
          <ToolIcon
            className={cn(
              "h-4 w-4 shrink-0",
              isRunning
                ? "text-brand animate-pulse"
                : hasSpecialRenderer
                  ? "text-primary"
                  : "text-muted-foreground",
            )}
          />
          {isRunning ? (
            <span className="text-foreground/80 flex min-w-0 items-center gap-1.5 text-sm font-medium">
              <span className="truncate">{liveCaption}</span>
              <span className="flex shrink-0 gap-0.5" aria-hidden="true">
                <span className="bg-brand/70 h-1 w-1 animate-bounce rounded-full [animation-delay:0ms]" />
                <span className="bg-brand/70 h-1 w-1 animate-bounce rounded-full [animation-delay:150ms]" />
                <span className="bg-brand/70 h-1 w-1 animate-bounce rounded-full [animation-delay:300ms]" />
              </span>
            </span>
          ) : (
            <span className="truncate text-sm font-medium">{friendlyName}</span>
          )}
          {inputHint && !isRunning ? (
            <span className="text-muted-foreground min-w-0 flex-1 truncate text-xs italic">
              {inputHint}
            </span>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {isRunning ? (
            <Loader2 className="text-brand h-4 w-4 animate-spin" aria-label="Running" />
          ) : (
            <>
              {isError ? (
                <XCircle className="text-destructive pop-in h-4 w-4 shrink-0" aria-label="Failed" />
              ) : (
                <CheckCircle2 className="text-brand pop-in h-4 w-4 shrink-0" aria-label="Done" />
              )}
              <Button
                variant="ghost"
                size="icon"
                className={cn(
                  "text-muted-foreground hover:bg-foreground/10 hover:text-foreground h-6 w-6 transition-colors",
                  showRaw && "text-primary",
                )}
                onClick={toggleRaw}
                title={showRaw ? "Show formatted view" : "Show arguments + raw output"}
                aria-label={showRaw ? "Show formatted view" : "Show arguments and raw output"}
              >
                <Code2 className="h-3.5 w-3.5" />
              </Button>
              {expanded ? (
                <ChevronUp className="text-muted-foreground h-4 w-4" />
              ) : (
                <ChevronDown className="text-muted-foreground h-4 w-4" />
              )}
            </>
          )}
        </div>
      </div>

      {/* Live progress shimmer — only while the step is in flight. */}
      {isRunning && (
        <div className="step-progress pointer-events-none absolute inset-x-0 bottom-0 h-0.5" />
      )}

      {expanded && (
        <CardContent className="px-3 pt-0 pb-3">
          {showRaw ? (
            <RawToolView toolCall={toolCall} resultText={resultText} />
          ) : toolCall.status === "completed" && isDateTime ? (
            <DateTimeResult result={resultText} />
          ) : toolCall.status === "completed" && isRAGSearch ? (
            <RAGSearchResults result={resultText} />
          ) : toolCall.status === "completed" && isWebSearch && webResults ? (
            <WebSearchResults data={webResults} />
          ) : isAskUser ? (
            <AskUserResult args={toolCall.args} resultText={resultText} />
          ) : (
            <GenericToolResult toolCall={toolCall} resultText={resultText} />
          )}
        </CardContent>
      )}
    </Card>
  );
}
