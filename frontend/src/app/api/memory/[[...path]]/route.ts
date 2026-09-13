import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL, forwardProjectHeaders } from "@/lib/server-api";

async function proxy(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  const token = request.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ detail: "请先登录" }, { status: 401 });
  const { path = [] } = await params;
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const valid =
    path.length === 0
      ? ["GET", "POST"].includes(request.method)
      : path.length === 1
        ? (path[0] === "settings" && request.method === "PUT") ||
          (["preview", "reindex"].includes(path[0] ?? "") && request.method === "POST") ||
          (uuid.test(path[0] ?? "") && ["PUT", "DELETE"].includes(request.method))
        : path.length === 2
          ? uuid.test(path[0] ?? "") &&
            ((["source", "history"].includes(path[1] ?? "") && request.method === "GET") ||
              (["archive", "restore"].includes(path[1] ?? "") && request.method === "POST"))
          : path.length === 3 &&
            uuid.test(path[1] ?? "") &&
            request.method === "POST" &&
            ((path[0] === "proposals" && ["accept", "reject"].includes(path[2] ?? "")) ||
              (path[0] === "jobs" && path[2] === "retry"));
  if (!valid) return NextResponse.json({ detail: "无效记忆路径" }, { status: 400 });
  try {
    const body = ["GET", "DELETE"].includes(request.method) ? undefined : await request.text();
    if (body && new TextEncoder().encode(body).length > 16000)
      return NextResponse.json({ detail: "记忆内容过长" }, { status: 413 });
    const query = new URLSearchParams();
    const revision = request.nextUrl.searchParams.get("revision");
    if (revision !== null) query.set("revision", revision);
    const response = await fetch(
      `${BACKEND_URL}/api/v1/memory${path.length ? "/" + path.join("/") : ""}?${query}`,
      {
        method: request.method,
        body,
        cache: "no-store",
        signal: AbortSignal.timeout(15000),
        headers: {
          ...forwardProjectHeaders(request),
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      },
    );
    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return NextResponse.json({ detail: "记忆服务暂时不可用，请稍后重试" }, { status: 502 });
  }
}
export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE };
