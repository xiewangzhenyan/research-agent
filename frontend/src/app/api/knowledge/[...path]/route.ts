import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/server-api";

async function proxy(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const token = request.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ detail: "请先登录" }, { status: 401 });
  const { path } = await params;
  if (!path.every((part) => /^[a-zA-Z0-9-]+$/.test(part)))
    return new NextResponse(null, { status: 400 });
  const headers = new Headers({ Authorization: `Bearer ${token}` });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  if (Number(request.headers.get("content-length") || 0) > 11 * 1024 * 1024)
    return NextResponse.json({ detail: "文件不能超过 10 MB" }, { status: 413 });
  try {
    const response = await fetch(`${BACKEND_URL}/api/v1/knowledge/${path.join("/")}`, {
      method: request.method,
      headers,
      cache: "no-store",
      body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer(),
      signal: AbortSignal.timeout(60000),
    });
    const outgoing = new Headers({
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    });
    for (const key of ["content-type", "content-disposition"]) {
      const value = response.headers.get(key);
      if (value) outgoing.set(key, value);
    }
    return new NextResponse(response.body, { status: response.status, headers: outgoing });
  } catch {
    return NextResponse.json({ detail: "知识库服务暂时不可用，请稍后重试" }, { status: 502 });
  }
}
export { proxy as GET, proxy as POST, proxy as DELETE, proxy as PUT };
