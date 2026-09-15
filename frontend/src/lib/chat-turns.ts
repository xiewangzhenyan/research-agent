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
      questions: {
        question: string;
        reason?: string;
        details?: string;
        required?: boolean;
        options?: string[];
        allow_custom?: boolean;
      }[];
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

export interface WorkTaskSelection {
  action: "new" | "continue" | "revise" | "replace" | "pause" | "cancel" | "complete";
  task_id?: string;
  expected_revision?: number;
}
export interface WorkTask {
  id: string;
  title: string;
  status: "active" | "paused" | "cancelled" | "completed";
  revision: number;
  source_valid: boolean;
  next_action: string;
  updated_at: string;
  requirements: { revision: number; content: string | null; valid: boolean }[];
  steps: {
    id: string;
    run_id: string | null;
    conversation_id: string | null;
    revision: number;
    status: ChatRun["status"];
    phase: string;
    historical: boolean;
  }[];
  artifacts: {
    id: string;
    run_id: string;
    name: string;
    size: number;
    revision: number;
    historical: boolean;
  }[];
}
