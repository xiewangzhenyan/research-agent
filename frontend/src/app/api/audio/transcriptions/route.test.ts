// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, expect, it, vi } from "vitest";
import { POST } from "./route";

function request(body: Uint8Array = new Uint8Array([1, 2, 3]), extra: Record<string, string> = {}) {
  return new NextRequest("https://app.test/api/audio/transcriptions", {
    method: "POST",
    body: body as Uint8Array<ArrayBuffer>,
    headers: { cookie: "access_token=session", "content-type": "audio/wav", ...extra },
  });
}
afterEach(() => vi.unstubAllGlobals());
it("rejects missing authentication, wrong origin, oversized and wrong-format audio before forwarding", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  for (const [headers, status] of [
    [{ cookie: "" }, 401],
    [{ origin: "https://other.test" }, 403],
    [{ "content-type": "audio/webm" }, 415],
    [{ "content-length": "999999999" }, 413],
  ] as const) {
    expect((await POST(request(undefined, headers))).status).toBe(status);
  }
  expect((await POST(request(new Uint8Array(2 * 1024 * 1024 + 1)))).status).toBe(413);
  expect(fetcher).not.toHaveBeenCalled();
});
it("forwards only WAV and cookie authorization; exposes no ASR keys or model overrides", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(Response.json({ text: "测试", model: "Qwen/Qwen3-ASR-1.7B" }));
  vi.stubGlobal("fetch", fetcher);
  const response = await POST(
    request(undefined, { "x-model": "arbitrary", "x-api-key": "untrusted" }),
  );
  expect(response.status).toBe(200);
  expect(response.headers.get("cache-control")).toBe("private, no-store");
  expect(fetcher.mock.calls[0]![1].headers).toEqual({
    Authorization: "Bearer session",
    "Content-Type": "audio/wav",
  });
  expect(await response.json()).toMatchObject({ text: "测试" });
});
it("hides unexpected backend diagnostics", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(Response.json({ detail: "private-service-address" }, { status: 500 })),
  );
  const response = await POST(request());
  expect(response.status).toBe(502);
  expect(await response.text()).not.toContain("private-service-address");
});
