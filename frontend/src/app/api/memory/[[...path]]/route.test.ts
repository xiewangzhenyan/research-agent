import { afterEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { DELETE, GET, POST } from "./route";

afterEach(() => vi.unstubAllGlobals());
const id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
it("requires authentication before backend access", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  expect(
    (await GET(new NextRequest("https://app.test/api/memory"), { params: Promise.resolve({}) }))
      .status,
  ).toBe(401);
  expect(fetcher).not.toHaveBeenCalled();
});
it("preserves project isolation, revision and an empty deletion response", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetcher);
  const response = await DELETE(
    new NextRequest(`https://app.test/api/memory/${id}?revision=7`, {
      method: "DELETE",
      headers: { cookie: "access_token=fixture", "X-Project-ID": id },
    }),
    { params: Promise.resolve({ path: [id] }) },
  );
  expect(response.status).toBe(204);
  expect(await response.text()).toBe("");
  expect(response.headers.get("Cache-Control")).toBe("private, no-store");
  expect(fetcher).toHaveBeenCalledWith(
    expect.stringContaining(`/${id}?revision=7`),
    expect.objectContaining({
      method: "DELETE",
      cache: "no-store",
      headers: {
        Authorization: "Bearer fixture",
        "X-Project-ID": id,
        "Content-Type": "application/json",
      },
    }),
  );
});
it("rejects traversal and oversized writes before contacting backend", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  const headers = { cookie: "access_token=fixture" };
  expect(
    (
      await GET(new NextRequest("https://app.test/api/memory/users", { headers }), {
        params: Promise.resolve({ path: ["..", "users"] }),
      })
    ).status,
  ).toBe(400);
  expect(
    (
      await POST(
        new NextRequest("https://app.test/api/memory", {
          method: "POST",
          headers,
          body: "字".repeat(6000),
        }),
        { params: Promise.resolve({}) },
      )
    ).status,
  ).toBe(413);
  expect(fetcher).not.toHaveBeenCalled();
});
it("preserves backend denials and does not broaden default scope", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response('{"detail":"missing"}', { status: 404 }));
  vi.stubGlobal("fetch", fetcher);
  const response = await GET(
    new NextRequest(`https://app.test/api/memory/${id}/source`, {
      headers: { cookie: "access_token=fixture" },
    }),
    { params: Promise.resolve({ path: [id, "source"] }) },
  );
  expect(response.status).toBe(404);
  expect(fetcher.mock.calls[0]![1].headers["X-Project-ID"]).toBeUndefined();
});
