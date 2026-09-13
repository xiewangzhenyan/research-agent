import { afterEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";
import { backendFetch, BackendApiError } from "@/lib/server-api";

vi.mock("@/lib/server-api", async (original) => ({
  ...(await original<typeof import("@/lib/server-api")>()),
  backendFetch: vi.fn(),
}));
afterEach(() => vi.clearAllMocks());
it("rejects a missing login cookie without making an upstream request", async () => {
  const response = await GET(new NextRequest("https://app.test/api/agent/generation-config"));
  expect(response.status).toBe(401);
  expect(backendFetch).not.toHaveBeenCalled();
});
it("translates the login cookie into backend authorization and prevents shared caching", async () => {
  vi.mocked(backendFetch).mockResolvedValue({ default: "configured-model" });
  const response = await GET(
    new NextRequest("https://app.test/api/agent/generation-config", {
      headers: { cookie: "access_token=test-session" },
    }),
  );
  expect(backendFetch).toHaveBeenCalledWith("/api/v1/agent/generation-config", {
    headers: { Authorization: "Bearer test-session" },
    cache: "no-store",
    signal: expect.any(AbortSignal),
  });
  expect(response.headers.get("Cache-Control")).toBe("private, no-store");
  expect(await response.json()).toEqual({ default: "configured-model" });
});
it("preserves authentication failure without exposing upstream errors", async () => {
  vi.mocked(backendFetch).mockRejectedValue(new BackendApiError(401, "private-service-address"));
  const response = await GET(
    new NextRequest("https://app.test/api/agent/generation-config", {
      headers: { cookie: "access_token=expired" },
    }),
  );
  expect(response.status).toBe(401);
  expect(JSON.stringify(await response.json())).not.toContain("private-service-address");
});
