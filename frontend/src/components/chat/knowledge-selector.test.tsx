import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { KnowledgeSelector } from "./knowledge-selector";
import { useKnowledgeStore } from "@/stores/knowledge-store";
import { useAuthStore, useConversationStore } from "@/stores";
import type { User } from "@/types";

beforeEach(() => {
  useAuthStore.getState().setUser({ id: "owner" } as User);
  useKnowledgeStore.getState().reset();
  useConversationStore.getState().setCurrentConversationId("conversation-a");
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
function mount() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><KnowledgeSelector /></QueryClientProvider>);
}
it("restores saved scope and keeps unavailable selections visible", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(url.includes("/conversations/") ? { active_knowledge_base_ids: ["removed-base"], knowledge_strict: true } : { items: [] }))));
  mount();
  await screen.findByRole("alert");
  expect(useKnowledgeStore.getState().ids).toEqual(["removed-base"]);
  expect(useKnowledgeStore.getState().error).toContain("不可用");
});
it("ignores a previous conversation response after switching", async () => {
  let resolveOld!: (r: Response) => void;
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    if (url.endsWith("conversation-a")) return new Promise<Response>((resolve) => { resolveOld = resolve; });
    return Promise.resolve(new Response(JSON.stringify(url.includes("/conversations/") ? { active_knowledge_base_ids: ["base-b"], knowledge_strict: false } : { items: [{ id: "base-b", name: "新范围" }] })));
  }));
  mount();
  act(() => useConversationStore.getState().setCurrentConversationId("conversation-b"));
  await waitFor(() => expect(useKnowledgeStore.getState().ids).toEqual(["base-b"]));
  await act(async () => resolveOld(new Response(JSON.stringify({ active_knowledge_base_ids: ["private-old"] }))));
  expect(useKnowledgeStore.getState().ids).toEqual(["base-b"]);
  expect(useKnowledgeStore.getState().strict).toBe(false);
});
it("restores a document scope without widening to the entire base", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(url.includes("/conversations/") ? { active_knowledge_base_ids: ["base-a"], active_knowledge_document_ids: ["paper-a"], knowledge_strict: true } : url.endsWith("/documents") ? [{ id: "paper-a", filename: "LSPR入门.pdf", status: "ready" }] : { items: [{ id: "base-a", name: "课题组资料" }] }))));
  mount();
  await waitFor(() => expect(useKnowledgeStore.getState().documentsReady).toBe(true));
  expect(useKnowledgeStore.getState().documentIds).toEqual(["paper-a"]);
  expect(screen.getByLabelText("仅检索：LSPR入门.pdf")).toBeChecked();
  expect(screen.getByText("仅使用 1 条资料 · 严格资料问答")).toBeVisible();
});
it("keeps a deleted document selected and blocks sending until the user changes scope", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(url.includes("/conversations/") ? { active_knowledge_base_ids: ["base-a"], active_knowledge_document_ids: ["removed-paper"] } : url.endsWith("/documents") ? [] : { items: [{ id: "base-a", name: "课题组资料" }] }))));
  mount();
  await screen.findByRole("alert");
  expect(useKnowledgeStore.getState().documentIds).toEqual(["removed-paper"]);
  expect(useKnowledgeStore.getState().error).toContain("资料");
});
