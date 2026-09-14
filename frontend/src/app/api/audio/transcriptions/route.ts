import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/server-api";

const MAX_BYTES = 2 * 1024 * 1024;
const headers = { "Cache-Control": "private, no-store" };
function failure(status: number, detail: string) {
  return NextResponse.json({ detail }, { status, headers });
}

export async function POST(request: NextRequest) {
  const token = request.cookies.get("access_token")?.value;
  if (!token) return failure(401, "请先登录");
  const origin = request.headers.get("origin");
  let sameHost = true;
  if (origin) {
    try {
      const parsed = new URL(origin);
      // TLS may terminate at the reverse proxy, so compare the public Host.
      sameHost =
        ["https:", "http:"].includes(parsed.protocol) &&
        parsed.host === (request.headers.get("host") || request.nextUrl.host);
    } catch {
      sameHost = false;
    }
  }
  if (request.headers.get("sec-fetch-site") === "cross-site" || !sameHost)
    return failure(403, "请求来源无效");
  if (request.headers.get("content-type")?.split(";", 1)[0] !== "audio/wav")
    return failure(415, "请使用浏览器录音");
  const length = request.headers.get("content-length");
  if (length && (!/^\d+$/.test(length) || Number(length) > MAX_BYTES))
    return failure(413, "录音不能超过 2 MB");
  if (!request.body) return failure(400, "录音为空");
  const reader = request.body.getReader();
  const uploadSignal = AbortSignal.any([request.signal, AbortSignal.timeout(15000)]);
  const cancelRead = () => {
    void reader.cancel().catch(() => {});
  };
  uploadSignal.addEventListener("abort", cancelRead, { once: true });
  try {
    const parts: Uint8Array[] = [];
    let total = 0;
    while (true) {
      uploadSignal.throwIfAborted();
      const { done, value } = await reader.read();
      uploadSignal.throwIfAborted();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_BYTES) {
        cancelRead();
        return failure(413, "录音不能超过 2 MB");
      }
      parts.push(value);
    }
    if (!total) return failure(400, "录音为空");
    const audio = new Uint8Array(total);
    let offset = 0;
    for (const part of parts) {
      audio.set(part, offset);
      offset += part.length;
    }
    const response = await fetch(`${BACKEND_URL}/api/v1/audio/transcriptions`, {
      method: "POST",
      body: audio,
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "audio/wav" },
      cache: "no-store",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(105000)]),
    });
    if (response.status >= 500 && response.status !== 503)
      return failure(502, "语音转写暂时失败，请重试");
    return NextResponse.json(await response.json(), { status: response.status, headers });
  } catch {
    return failure(502, "语音连接中断或超时，录音已保留，可点击重试");
  } finally {
    uploadSignal.removeEventListener("abort", cancelRead);
    reader.releaseLock();
  }
}
