import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/server-api";

async function proxy(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  const token = request.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ detail: "请先登录" }, { status: 401 });
  const { path = [] } = await params;
  const valid =
    path.length === 0
      ? ["GET", "POST"].includes(request.method)
      : path.length === 1 &&
        ["GET", "PUT"].includes(request.method) &&
        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(path[0] ?? "");
  if (!valid) return NextResponse.json({ detail: "无效项目路径" }, { status: 400 });
  try {
    const body = request.method === "GET" ? undefined : await request.text();
    if (body && new TextEncoder().encode(body).length > 10000)
      return NextResponse.json({ detail: "内容过长" }, { status: 413 });
    const response = await fetch(
      `${BACKEND_URL}/api/v1/projects${path.length ? "/" + path[0] : ""}`,
      {
        method: request.method,
        body,
        cache: "no-store",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        signal: AbortSignal.timeout(15000),
      },
    );
    return new NextResponse(response.body, {
      status: response.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "private, no-store" },
    });
  } catch {
    return NextResponse.json({ detail: "项目服务暂时不可用" }, { status: 502 });
  }
}
export { proxy as GET, proxy as POST, proxy as PUT };
