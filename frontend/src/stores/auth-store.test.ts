import { describe, expect, it } from "vitest";
import { useAuthStore } from "./auth-store";
import { useKnowledgeStore } from "./knowledge-store";
import { useSourcesPanelStore } from "./sources-panel-store";
import { useChatStore } from "./chat-store";
import { useConversationStore } from "./conversation-store";
import { useFilePreviewStore } from "./file-preview-store";
import type { User } from "@/types";

describe("private account views", () => {
  it("clears previous documents, sources and conversations on direct account switch", () => {
    useAuthStore.getState().setUser({ id: "account-a" } as User);
    useKnowledgeStore.getState().setIds(["private-base"]);
    useKnowledgeStore.setState({ documentIds: ["private-paper"], documentsReady: true });
    useSourcesPanelStore.getState().open([{ index: 1, type: "rag", title: "Private source", content: "Account A secret" }]);
    useChatStore.getState().addMessage({ id: "private-message", role: "assistant", content: "Account A secret", timestamp: new Date() });
    useConversationStore.getState().setCurrentConversationId("private-conversation");
    useFilePreviewStore.getState().open({ id: "private-file", filename: "secret.txt", mime_type: "text/plain", file_type: "text" });
    useAuthStore.getState().setUser({ id: "account-b" } as User);
    expect(useKnowledgeStore.getState().ids).toEqual([]);
    expect(useKnowledgeStore.getState().documentIds).toBeNull();
    expect(useKnowledgeStore.getState().documentsReady).toBe(false);
    expect(useSourcesPanelStore.getState().sources).toEqual([]);
    expect(useSourcesPanelStore.getState().isOpen).toBe(false);
    expect(useChatStore.getState().messages).toEqual([]);
    expect(useConversationStore.getState().currentConversationId).toBeNull();
    expect(useFilePreviewStore.getState().file).toBeNull();
    useAuthStore.getState().logout();
  });
});
