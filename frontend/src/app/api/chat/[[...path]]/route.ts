import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL, forwardProjectHeaders } from "@/lib/server-api";

async function proxy(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  const token = request.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ detail: "请先登录" }, { status: 401 });
  const { path = [] } = await params;
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const isExport =
    request.method === "POST" &&
    path.length === 3 &&
    path[0] === "messages" &&
    uuid.test(path[1] ?? "") &&
    path[2] === "export";
  const valid =
    isExport ||
    (request.method === "GET" &&
      path[0] === "work-tasks" &&
      (path.length === 1 || (path.length === 2 && uuid.test(path[1] ?? "")))) ||
    (request.method === "GET" &&
      path.length === 5 &&
      path[0] === "conversations" &&
      uuid.test(path[1] ?? "") &&
      path[2] === "messages" &&
      uuid.test(path[3] ?? "") &&
      path[4] === "context") ||
    (request.method === "POST" && path.length === 1 && path[0] === "turns") ||
    (request.method === "GET" &&
      path.length === 3 &&
      path[0] === "conversations" &&
      uuid.test(path[1] ?? "") &&
      path[2] === "state");
  if (!valid) return NextResponse.json({ detail: "无效对话路径" }, { status: 400 });
  const query = new URLSearchParams();
  for (const key of ["before", "include_messages", "conversation_id"]) {
    const value = request.nextUrl.searchParams.get(key);
    if (value !== null) query.set(key, value);
  }
  try {
    const body = request.method === "POST" ? await request.text() : undefined;
    if (body && new TextEncoder().encode(body).length > 150000)
      return NextResponse.json({ detail: "消息过长，请拆分后发送" }, { status: 413 });
    const response = await fetch(`${BACKEND_URL}/api/v1/chat/${path.join("/")}?${query}`, {
      method: request.method,
      body,
      cache: "no-store",
      headers: {
        ...forwardProjectHeaders(request),
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      // Accepting the message is independent of the browser's connection lifetime.
      signal: AbortSignal.timeout(15000),
    });
    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        "Content-Type":
          isExport && response.ok
            ? (response.headers.get("Content-Type") ?? "application/octet-stream")
            : "application/json",
        ...(isExport && response.ok && response.headers.get("Content-Disposition")
          ? { "Content-Disposition": response.headers.get("Content-Disposition")! }
          : {}),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
      },
    });
  } catch {
    return NextResponse.json(
      {
        detail: isExport
          ? "导出暂时失败，请稍后重试"
          : "发送结果暂未确认，请重试；相同消息不会重复提交",
      },
      { status: 502 },
    );
  }
}

export { proxy as GET, proxy as POST };
