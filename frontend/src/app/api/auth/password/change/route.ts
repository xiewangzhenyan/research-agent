import { NextRequest, NextResponse } from "next/server";
import { backendFetch, BackendApiError } from "@/lib/server-api";

export async function POST(request: NextRequest) {
  const accessToken = request.cookies.get("access_token")?.value;
  if (!accessToken) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  try {
    const body = await request.json();
    await backendFetch("/api/v1/auth/password/change", {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify(body),
    });
    return new NextResponse(null, { status: 204 });
  } catch (error) {
    if (error instanceof BackendApiError) {
      const detail = (error.data as { detail?: unknown })?.detail;
      return NextResponse.json({ detail: detail || error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Invalid request" }, { status: 400 });
  }
}
