import type { EffectiveConfig, GenerationOptions } from "@/lib/model-capabilities";
import type { RawMessage } from "@/lib/conversation-to-chat";

export interface ChatRun {
  id: string;
  conversation_id: string;
  user_message_id: string;
  assistant_message_id: string;
  status:
    "queued" | "running" | "waiting_input" | "cancelling" | "completed" | "cancelled" | "failed";
  created_at: string;
  event_seq: number;
  attempt: number;
  request: { prompt?: string; routing?: { route: string; reason: string } | null };
  effective_config: EffectiveConfig;
  result: { content: string; thinking?: string; partial?: boolean } | null;
  error: string | null;
  pending_input: {
    question_id: string;
    calls: {
      call_id: string;
      questions: { question: string; options?: string[]; allow_custom?: boolean }[];
    }[];
  } | null;
}

export interface ChatSnapshot {
  generation?: GenerationOptions;
  messages?: RawMessage[];
  before?: string | null;
  runs: ChatRun[];
}

export const activeRun = (run: ChatRun) =>
  ["queued", "running", "waiting_input", "cancelling"].includes(run.status);
export const lastChatKey = (userId: string, projectId?: string) =>
  `research-agent:last-chat:${userId}:${projectId ?? "default"}`;

export type ChatRatingUpdate = (
  id: string,
  rating: number | null,
  counts: { likes: number; dislikes: number },
) => void;
