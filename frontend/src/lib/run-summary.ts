import type { ChatMessage, ToolCall } from "@/types";

/** Tool calls of an answer, from the ordered parts timeline or the legacy list. */
export function toolCallsOf(message: Pick<ChatMessage, "parts" | "toolCalls">): ToolCall[] {
  const fromParts = (message.parts ?? []).flatMap((part) =>
    part.type === "tool" && part.toolCall ? [part.toolCall] : [],
  );
  return fromParts.length > 0 ? fromParts : (message.toolCalls ?? []);
}

export interface RetrievalSummary {
  passages: number;
  documents: number;
}

/** Passage and distinct-document counts for a knowledge search result list. */
export function summarizeRetrieval(items: { source: string }[]): RetrievalSummary | null {
  if (items.length === 0) return null;
  return { passages: items.length, documents: new Set(items.map((i) => i.source)).size };
}
