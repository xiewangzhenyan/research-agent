import { NextRequest, NextResponse } from "next/server";
import { backendFetch, BackendApiError } from "@/lib/server-api";

export async function GET(request: NextRequest) {
  const token = request.cookies.get("access_token")?.value;
  const headers = { "Cache-Control": "private, no-store" };
  if (!token) return NextResponse.json({ detail: "请先登录" }, { status: 401, headers });
  try {
    const data = await backendFetch("/api/v1/audio/config", {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
    return NextResponse.json(data, { headers });
  } catch (error) {
    const status =
      error instanceof BackendApiError && [401, 403].includes(error.status) ? error.status : 502;
    return NextResponse.json({ detail: "语音配置暂不可用" }, { status, headers });
  }
}
