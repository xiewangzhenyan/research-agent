import type { ChatMessage } from "@/types";
export type ChatArtifact = {
  id: string;
  run_id: string;
  name: string;
  size: number;
  mime_type: string;
};
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function extractArtifacts(message: ChatMessage): ChatArtifact[] {
  const runId = message.execution?.id;
  if (!runId || !uuid.test(runId)) return [];
  const result = new Map<string, ChatArtifact>();
  const calls = [
    ...(message.toolCalls ?? []),
    ...(message.parts ?? []).flatMap((p) => (p.toolCall ? [p.toolCall] : [])),
  ];
  for (const call of calls) {
    if (!["create_document", "run_python"].includes(call.name) || call.status !== "completed")
      continue;
    try {
      if (typeof call.result === "string" && call.result.length > 200000) continue;
      const payload = typeof call.result === "string" ? JSON.parse(call.result) : call.result;
      if (!Array.isArray(payload?.artifacts)) continue;
      for (const item of payload.artifacts.slice(0, 200)) {
        if (
          typeof item?.id === "string" &&
          uuid.test(item.id) &&
          item.run_id === runId &&
          typeof item.name === "string" &&
          item.name.length <= 120 &&
          typeof item.mime_type === "string" &&
          Number.isInteger(item.size) &&
          item.size >= 0 &&
          item.size <= 2097152
        ) {
          result.set(item.id, {
            id: item.id,
            run_id: runId,
            name: item.name,
            size: item.size,
            mime_type: item.mime_type,
          });
          if (result.size >= 200) return [...result.values()];
        }
      }
    } catch {
      /* Ignore malformed historical tool results. Never use returned download URLs. */
    }
  }
  return [...result.values()];
}
