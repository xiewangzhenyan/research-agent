import { afterEach, beforeEach, expect, it, vi } from "vitest";
const state = vi.hoisted(() => ({ user: "a", project: "alpha", setAccessToken: vi.fn() }));
vi.mock("@/stores", () => ({
  useAuthStore: {
    getState: () => ({ user: { id: state.user }, setAccessToken: state.setAccessToken }),
  },
}));
vi.mock("@/lib/project-scope", () => ({
  projectHeaders: () => ({ "X-Project-ID": state.project }),
}));
import { apiClient } from "./api-client";
import { capabilityFetch } from "./capabilities";
beforeEach(() => {
  state.user = "a";
  state.project = "alpha";
});
afterEach(() => vi.unstubAllGlobals());
it("pins a binding write to the original project across token refresh", async () => {
  const attempts: RequestInit[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      if (url.endsWith("/auth/refresh")) {
        state.project = "beta";
        return new Response('{"access_token":"dummy"}');
      }
      attempts.push(init);
      return new Response("{}", { status: attempts.length === 1 ? 401 : 200 });
    }),
  );
  await apiClient.put("/capabilities/bindings", { asset_ids: ["asset"], revision: "x" });
  expect(attempts).toHaveLength(2);
  expect(attempts.map((a) => (a.headers as Record<string, string>)["X-Project-ID"])).toEqual([
    "alpha",
    "alpha",
  ]);
});
it("pins multipart imports to the selected project across refresh", async () => {
  const attempts: RequestInit[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      if (url.endsWith("/auth/refresh")) {
        state.project = "beta";
        return new Response('{"access_token":"dummy"}');
      }
      attempts.push(init);
      return new Response("{}", { status: attempts.length === 1 ? 401 : 200 });
    }),
  );
  await capabilityFetch("skills/import", { method: "POST", body: "fixture" });
  expect(attempts.map((a) => (a.headers as Record<string, string>)["X-Project-ID"])).toEqual([
    "alpha",
    "alpha",
  ]);
});
it.each(["json", "multipart"])("never retries a %s write under another account", async (kind) => {
  let attempts = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/auth/refresh")) {
        state.user = "b";
        return new Response('{"access_token":"dummy"}');
      }
      attempts++;
      return new Response("{}", { status: 401 });
    }),
  );
  const action =
    kind === "json"
      ? apiClient.post("/capabilities/mcp", { name: "a" })
      : capabilityFetch("skills/import", { method: "POST", body: "fixture" });
  await expect(action).rejects.toThrow("账号已切换");
  expect(attempts).toBe(1);
});
