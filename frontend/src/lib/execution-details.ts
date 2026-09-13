import type { RoleEvent } from "@/components/tasks/collaboration-progress";
import type { ExecutionResult } from "@/components/tasks/code-execution-panel";
import type { RetrievalRecord, RetrievalSnapshot } from "@/components/tasks/retrieval-settings";
import type { ChatRun } from "./chat-turns";

export type Execution = Omit<ChatRun, "conversation_id" | "request" | "result"> & {
  conversation_id: string | null;
  request: ChatRun["request"] & {
    knowledge_base_ids?: string[];
    tools?: string[];
    mode?: string;
    retrieval_snapshot?: RetrievalSnapshot;
  };
  result:
    | (NonNullable<ChatRun["result"]> & {
        retrieval_runs?: RetrievalRecord[];
        citations?: {
          index: number;
          title?: string;
          filename?: string;
          document_name?: string;
          content: string;
          quotes?: string[];
          page?: number;
          page_number?: number;
        }[];
      })
    | null;
};
export type ExecutionEvent = RoleEvent & {
  created_at: string;
  data: RoleEvent["data"] & ExecutionResult & { tool?: string; retrieval?: RetrievalRecord };
};
export const executionFinished = (status: string) =>
  ["completed", "cancelled", "failed"].includes(status);
export const executionIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
