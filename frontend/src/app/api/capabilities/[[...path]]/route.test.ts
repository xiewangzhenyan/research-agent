import { afterEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST, DELETE } from "./route";
const id = "dddddddd-4444-4444-8444-444444444444";
const headers = { cookie: "access_token=dummy", "X-Project-ID": id };
afterEach(() => vi.unstubAllGlobals());
it("rejects unauthenticated requests and non-allowlisted routes", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  expect(
    (
      await GET(new NextRequest("http://localhost/api/capabilities/mcp"), {
        params: Promise.resolve({ path: ["mcp"] }),
      })
    ).status,
  ).toBe(401);
  for (const path of [
    ["assets", "../other", "test"],
    ["assets", id, "test", "extra"],
    ["assets", id, "export"],
  ]) {
    const response = await POST(
      new NextRequest("http://localhost/api/capabilities/mcp", {
        method: "POST",
        headers,
        body: "{}",
      }),
      { params: Promise.resolve({ path }) },
    );
    expect(response.status).toBe(400);
  }
  expect(fetch).not.toHaveBeenCalled();
});
it("preserves multipart bytes and authenticated project scope", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response("{}"));
  vi.stubGlobal("fetch", fetch);
  const data =
    '--test-boundary\r\nContent-Disposition: form-data; name="file"; filename="SKILL.md"\r\n\r\nskill test\r\n--test-boundary--\r\n';
  const response = await POST(
    new NextRequest("http://localhost/api/capabilities/skills/import?user_id=attacker", {
      method: "POST",
      headers: { ...headers, "Content-Type": "multipart/form-data; boundary=test-boundary" },
      body: data,
    }),
    { params: Promise.resolve({ path: ["skills", "import"] }) },
  );
  expect(response.status).toBe(200);
  const [url, init] = fetch.mock.calls[0]!;
  expect(url).not.toContain("user_id");
  expect(init.headers["X-Project-ID"]).toBe(id);
  expect(init.headers.Authorization).toBe("Bearer dummy");
  expect(new TextDecoder().decode(init.body)).toContain("skill test");
  expect(init.headers["Content-Type"]).toContain("multipart/form-data; boundary=");
});
it("preserves conflicts and passes only revision to delete", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response('{"detail":"stale"}', { status: 409 }));
  vi.stubGlobal("fetch", fetch);
  const response = await DELETE(
    new NextRequest(`http://localhost/api/capabilities/assets/${id}?revision=7&owner_id=forged`, {
      method: "DELETE",
      headers,
    }),
    { params: Promise.resolve({ path: ["assets", id] }) },
  );
  expect(response.status).toBe(409);
  expect(fetch.mock.calls[0]![0]).toMatch(/revision=7$/);
  expect(response.headers.get("Cache-Control")).toBe("private, no-store");
});
it("retains ZIP download bytes and headers", async () => {
  const bytes = new Uint8Array([80, 75, 0, 255]);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(bytes, {
        headers: {
          "Content-Type": "application/zip",
          "Content-Disposition": "attachment; filename=skill.zip",
        },
      }),
    ),
  );
  const response = await GET(
    new NextRequest(`http://localhost/api/capabilities/assets/${id}/export`, { headers }),
    { params: Promise.resolve({ path: ["assets", id, "export"] }) },
  );
  expect(new Uint8Array(await response.arrayBuffer())).toEqual(bytes);
  expect(response.headers.get("Content-Disposition")).toContain("skill.zip");
});
it("rejects oversized bodies before contacting the backend", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const response = await POST(
    new NextRequest("http://localhost/api/capabilities/mcp", {
      method: "POST",
      headers: { ...headers, "Content-Length": "9000000" },
      body: "{}",
    }),
    { params: Promise.resolve({ path: ["mcp"] }) },
  );
  expect(response.status).toBe(413);
  expect(fetch).not.toHaveBeenCalled();
});
