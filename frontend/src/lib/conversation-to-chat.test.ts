import { expect, it } from "vitest";
import { conversationMessageToChatMessage } from "./conversation-to-chat";

it("restores the saved answer policy without applying today's defaults", () => {
  const saved = {
    model: "previous-model",
    temperature: 0.25,
    thinking_effort: null,
    policy_version: "previous-policy",
  };
  const message = conversationMessageToChatMessage({
    id: "answer",
    conversation_id: "conversation",
    role: "assistant",
    content: "answer",
    created_at: "2026-09-10T00:00:00Z",
    effective_config: saved,
  });
  expect(message.effectiveConfig).toEqual(saved);
  expect(message.parts?.[0]?.content).toBe("answer");
  const oldMessage = conversationMessageToChatMessage({
    id: "old",
    conversation_id: "conversation",
    role: "assistant",
    content: "old answer",
    created_at: "2026-09-09T00:00:00Z",
  });
  expect(oldMessage.effectiveConfig).toBeUndefined();
});
