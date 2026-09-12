import { NextRequest, NextResponse } from "next/server";
import { backendFetch, BackendApiError } from "@/lib/server-api";

export async function GET(request: NextRequest) {
  const token = request.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ detail: "请先登录" }, { status: 401 });
  try {
    const data = await backendFetch("/api/v1/agent/capabilities", {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    return NextResponse.json(data, { headers: { "Cache-Control": "private, no-store" } });
  } catch (error) {
    return NextResponse.json(
      { detail: "模型配置暂时无法加载，请稍后重试。" },
      { status: error instanceof BackendApiError ? error.status : 500 },
    );
  }
}
