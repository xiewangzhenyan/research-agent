import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useAuthStore } from "@/stores/auth-store";
import type { User } from "@/types";
import { activateProject, currentProject, projectFetch, projectHeaders } from "./project-scope";

beforeEach(() => useAuthStore.getState().setUser({ id: "owner" } as User));
afterEach(() => {
  activateProject("owner", null);
  vi.unstubAllGlobals();
});

it("forwards a fixed project header and preserves content type and cancellation", async () => {
  const project = {
    id: "project-a",
    name: "A",
    description: "",
    knowledge_base_ids: ["account-kb"],
  };
  activateProject("owner", project);
  const fetcher = vi.fn().mockResolvedValue(new Response("{}"));
  vi.stubGlobal("fetch", fetcher);
  const controller = new AbortController();
  await projectFetch("/api/tasks", {
    headers: { "Content-Type": "application/json" },
    signal: controller.signal,
  });
  const init = fetcher.mock.calls[0]![1];
  expect(init.headers.get("X-Project-ID")).toBe("project-a");
  expect(init.headers.get("Content-Type")).toBe("application/json");
  expect(init.signal).toBe(controller.signal);
  expect(currentProject()?.knowledge_base_ids).toEqual(["account-kb"]);
});

it("never inherits a previous account's selected project", () => {
  activateProject("owner", {
    id: "private-project",
    name: "A",
    description: "",
    knowledge_base_ids: ["private-kb"],
  });
  useAuthStore.getState().setUser({ id: "other" } as User);
  expect(projectHeaders()).toEqual({});
  expect(currentProject()).toBeNull();
});

it("removes stale headers in the default workspace", async () => {
  activateProject("owner", null);
  const fetcher = vi.fn().mockResolvedValue(new Response("{}"));
  vi.stubGlobal("fetch", fetcher);
  await projectFetch("/api/tasks", { headers: { "X-Project-ID": "stale-project" } });
  expect(fetcher.mock.calls[0]![1].headers.has("X-Project-ID")).toBe(false);
});
