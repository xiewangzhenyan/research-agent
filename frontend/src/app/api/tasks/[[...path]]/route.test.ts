import { afterEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "./route";

afterEach(() => vi.unstubAllGlobals());
it("requires login before contacting the backend", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  const response = await GET(new NextRequest("https://app.test/api/tasks"), {
    params: Promise.resolve({}),
  });
  expect(response.status).toBe(401);
  expect(fetcher).not.toHaveBeenCalled();
});
it("forwards cookie authentication and replay cursor without shared caching", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response("[]", { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  const id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
  const response = await GET(
    new NextRequest(`https://app.test/api/tasks/${id}/events?after=17`, {
      headers: { cookie: "access_token=session" },
    }),
    { params: Promise.resolve({ path: [id, "events"] }) },
  );
  expect(fetcher).toHaveBeenCalledWith(
    expect.stringContaining(`/api/v1/runs/${id}/events?after=17`),
    expect.objectContaining({
      headers: { Authorization: "Bearer session", "Content-Type": "application/json" },
      cache: "no-store",
    }),
  );
  expect(response.headers.get("Cache-Control")).toBe("private, no-store");
});
it("rejects non-task paths", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  const response = await GET(
    new NextRequest("https://app.test/api/tasks/anything", {
      headers: { cookie: "access_token=session" },
    }),
    { params: Promise.resolve({ path: ["..", "users"] }) },
  );
  expect(response.status).toBe(400);
  expect(fetcher).not.toHaveBeenCalled();
});
it("preserves owner denial on cancellation", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response('{"detail":"missing"}', { status: 404 })),
  );
  const id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
  const response = await POST(
    new NextRequest(`https://app.test/api/tasks/${id}/cancel`, {
      method: "POST",
      headers: { cookie: "access_token=session" },
    }),
    { params: Promise.resolve({ path: [id, "cancel"] }) },
  );
  expect(response.status).toBe(404);
});

it("permits only GET discovery for the tools path", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response('{"items":[]}', { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  const headers = { cookie: "access_token=session" };
  const response = await GET(new NextRequest("https://app.test/api/tasks/tools", { headers }), {
    params: Promise.resolve({ path: ["tools"] }),
  });
  expect(response.status).toBe(200);
  expect(fetcher).toHaveBeenCalledWith(
    expect.stringContaining("/api/v1/runs/tools"),
    expect.objectContaining({ method: "GET" }),
  );
  fetcher.mockClear();
  const denied = await POST(
    new NextRequest("https://app.test/api/tasks/tools", { method: "POST", headers }),
    { params: Promise.resolve({ path: ["tools"] }) },
  );
  expect(denied.status).toBe(400);
  expect(fetcher).not.toHaveBeenCalled();
});

it("preserves authenticated artifact download headers", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response("a,b", {
          headers: {
            "Content-Type": "text/csv",
            "Content-Disposition": "attachment; filename=data.csv",
          },
        }),
      ),
  );
  const id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
  const response = await GET(
    new NextRequest(`https://app.test/api/tasks/${id}/artifacts/${id}`, {
      headers: { cookie: "access_token=session" },
    }),
    { params: Promise.resolve({ path: [id, "artifacts", id] }) },
  );
  expect(response.headers.get("Content-Type")).toBe("text/csv");
  expect(response.headers.get("Content-Disposition")).toContain("attachment");
  expect(response.headers.get("X-Content-Type-Options")).toBe("nosniff");
  expect(await response.text()).toBe("a,b");
});
it("rejects artifact path traversal before contacting backend", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  const id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
  const response = await GET(
    new NextRequest("https://app.test/api/tasks", { headers: { cookie: "access_token=session" } }),
    { params: Promise.resolve({ path: [id, "artifacts", ".."] }) },
  );
  expect(response.status).toBe(400);
  expect(fetcher).not.toHaveBeenCalled();
});
