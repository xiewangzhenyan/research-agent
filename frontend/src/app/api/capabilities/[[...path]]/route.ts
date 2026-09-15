import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/server-api";

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function allowed(path: string[], method: string) {
  if (path.length === 1) {
    if (["skills", "mcp"].includes(path[0]!)) return ["GET", "POST"].includes(method);
    if (path[0] === "bindings") return ["GET", "PUT"].includes(method);
    return path[0] === "availability" && method === "GET";
  }
  if (
    path[0] === "skills" &&
    ["import", "import-directory"].includes(path[1]!) &&
    path.length === 2
  )
    return method === "POST";
  if (path[0] !== "assets" || !uuid.test(path[1] ?? "")) return false;
  if (path.length === 2) return ["GET", "PUT", "DELETE"].includes(method);
  if (path.length !== 3) return false;
  if (path[2] === "file") return ["GET", "PUT", "DELETE"].includes(method);
  if (["export", "versions"].includes(path[2]!)) return method === "GET";
  return ["test", "publish", "restore", "toggle"].includes(path[2]!) && method === "POST";
}
async function proxy(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  const token = request.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ detail: "请先登录" }, { status: 401 });
  const { path = [] } = await params;
  if (!allowed(path, request.method))
    return NextResponse.json({ detail: "无效能力路径" }, { status: 400 });
  const project = request.headers.get("X-Project-ID");
  if (project && !uuid.test(project))
    return NextResponse.json({ detail: "无效项目" }, { status: 400 });
  const limit = path[1]?.startsWith("import") ? 9 * 1024 * 1024 : 400000;
  if (Number(request.headers.get("content-length")) > limit)
    return NextResponse.json({ detail: "内容过大" }, { status: 413 });
  try {
    let body: ArrayBuffer | undefined;
    if (["POST", "PUT"].includes(request.method)) {
      const reader = request.body?.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      if (reader)
        while (true) {
          const part = await reader.read();
          if (part.done) break;
          size += part.value.byteLength;
          if (size > limit) {
            await reader.cancel();
            return NextResponse.json({ detail: "内容过大" }, { status: 413 });
          }
          chunks.push(part.value);
        }
      const value = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) {
        value.set(chunk, offset);
        offset += chunk.byteLength;
      }
      body = value.buffer;
    }
    const query = new URLSearchParams();
    for (const key of ["revision", "version", "path"]) {
      const value = request.nextUrl.searchParams.get(key);
      if (value !== null) query.set(key, value);
    }
    const response = await fetch(
      `${BACKEND_URL}/api/v1/capabilities/${path.join("/")}${query.size ? "?" + query : ""}`,
      {
        method: request.method,
        body,
        cache: "no-store",
        headers: {
          Authorization: `Bearer ${token}`,
          ...(body
            ? { "Content-Type": request.headers.get("content-type") || "application/json" }
            : {}),
          ...(project ? { "X-Project-ID": project } : {}),
        },
        signal: AbortSignal.timeout(35000),
      },
    );
    const headers = new Headers({
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    });
    for (const key of ["content-type", "content-disposition"]) {
      const v = response.headers.get(key);
      if (v) headers.set(key, v);
    }
    return new NextResponse(response.status === 204 ? null : response.body, {
      status: response.status,
      headers,
    });
  } catch {
    return NextResponse.json({ detail: "能力服务暂时不可用，请稍后重试" }, { status: 502 });
  }
}
export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE };
