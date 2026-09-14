import { afterEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "./route";

const id = "dddddddd-4444-4444-8444-444444444444";
const project = "ffffffff-6666-4666-8666-666666666666";
afterEach(() => vi.unstubAllGlobals());
const request = (cookie = "access_token=test-only") =>
  new NextRequest(`http://localhost/api/chat/messages/${id}/export`, {
    method: "POST",
    headers: { cookie, "Content-Type": "application/json", "X-Project-ID": project },
    body: JSON.stringify({ format: "docx" }),
  });
it("preserves binary bytes, attachment headers and project scope", async () => {
  const bytes = new Uint8Array([80, 75, 3, 4, 0, 255]);
  const fetch = vi.fn().mockResolvedValue(
    new Response(bytes, {
      headers: {
        "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "Content-Disposition": "attachment; filename*=UTF-8''report.docx",
      },
    }),
  );
  vi.stubGlobal("fetch", fetch);
  const result = await POST(request(), {
    params: Promise.resolve({ path: ["messages", id, "export"] }),
  });
  expect(new Uint8Array(await result.arrayBuffer())).toEqual(bytes);
  expect(result.headers.get("Content-Type")).toContain("wordprocessingml");
  expect(result.headers.get("Content-Disposition")).toContain("attachment");
  expect(result.headers.get("Cache-Control")).toBe("private, no-store");
  expect(fetch.mock.calls[0]![1].headers["X-Project-ID"]).toBe(project);
});
it("rejects missing auth and non-whitelisted paths without upstream calls", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  expect(
    (await POST(request(""), { params: Promise.resolve({ path: ["messages", id, "export"] }) }))
      .status,
  ).toBe(401);
  expect(
    (
      await POST(request(), {
        params: Promise.resolve({ path: ["messages", "../private", "export"] }),
      })
    ).status,
  ).toBe(400);
  expect(fetch).not.toHaveBeenCalled();
});

it("proxies only a scoped history disclosure and disables caching", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] })));
  vi.stubGlobal("fetch", fetch);
  const incoming = new NextRequest(
    `http://localhost/api/chat/conversations/${id}/messages/${id}/context`,
    {
      headers: { cookie: "access_token=test-only", "X-Project-ID": project },
    },
  );
  const response = await GET(incoming, {
    params: Promise.resolve({ path: ["conversations", id, "messages", id, "context"] }),
  });
  expect(response.status).toBe(200);
  expect(response.headers.get("Cache-Control")).toBe("private, no-store");
  expect(fetch.mock.calls[0]![1].headers["X-Project-ID"]).toBe(project);
  expect(
    (
      await GET(incoming, {
        params: Promise.resolve({ path: ["conversations", id, "messages", "../other", "context"] }),
      })
    ).status,
  ).toBe(400);
});
