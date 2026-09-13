import { NextRequest, NextResponse } from "next/server";
import { backendFetch, BackendApiError } from "@/lib/server-api";

export async function GET(request: NextRequest) {
  const headers = { "Cache-Control": "private, no-store" };
  const token = request.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ detail: "请先登录" }, { status: 401, headers });
  try {
    const data = await backendFetch("/api/v1/agent/generation-config", {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: request.signal,
    });
    return NextResponse.json(data, { headers });
  } catch (error) {
    return NextResponse.json(
      { detail: "模型配置暂时无法加载，请稍后重试。" },
      { status: error instanceof BackendApiError ? error.status : 500, headers },
    );
  }
}
