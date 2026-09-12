import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/server-api";

async function proxy(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  const token = request.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ detail: "请先登录" }, { status: 401 });
  const { path = [] } = await params;
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (
    path.length > 3 ||
    (path[0] &&
      !uuid.test(path[0]) &&
      !(path.length === 1 && path[0] === "tools" && request.method === "GET")) ||
    (path[1] && !["events", "cancel", "resume", "artifacts"].includes(path[1])) ||
    (path[2] && (path[1] !== "artifacts" || !uuid.test(path[2]))) ||
    (path[1] === "artifacts" &&
      !(request.method === "GET" || (path.length === 3 && request.method === "DELETE"))) ||
    (request.method === "DELETE" && (path.length !== 3 || path[1] !== "artifacts"))
  )
    return NextResponse.json({ detail: "无效任务路径" }, { status: 400 });
  const query = new URLSearchParams();
  for (const key of ["after", "offset"]) {
    const value = request.nextUrl.searchParams.get(key);
    if (value !== null) query.set(key, value);
  }
  try {
    const body = ["GET", "DELETE"].includes(request.method) ? undefined : await request.text();
    if (body && new TextEncoder().encode(body).length > 100000)
      return NextResponse.json({ detail: "任务内容过长" }, { status: 413 });
    const response = await fetch(
      `${BACKEND_URL}/api/v1/runs${path.length ? "/" + path.join("/") : ""}?${query}`,
      {
        method: request.method,
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        cache: "no-store",
        body,
        signal: AbortSignal.timeout(15000),
      },
    );
    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("Content-Type") || "application/json",
        ...(response.headers.get("Content-Disposition")
          ? { "Content-Disposition": response.headers.get("Content-Disposition")! }
          : {}),
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return NextResponse.json({ detail: "任务服务暂时不可用，请稍后重试" }, { status: 502 });
  }
}
export { proxy as GET, proxy as POST, proxy as DELETE };
