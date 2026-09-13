import { forwardProjectHeaders } from "@/lib/server-api";
import { NextRequest, NextResponse } from "next/server";

import { backendFetch, BackendApiError } from "@/lib/server-api";

export async function GET(request: NextRequest) {
  try {
    const accessToken = request.cookies.get("access_token")?.value;
    if (!accessToken) {
      return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }

    const qs = new URL(request.url).searchParams.toString();
    const data = await backendFetch(`/api/v1/conversations/tool-stats${qs ? `?${qs}` : ""}`, {
      headers: { Authorization: `Bearer ${accessToken}`, ...forwardProjectHeaders(request) },
    });

    return NextResponse.json(data, { headers: { "Cache-Control": "private, no-store" } });
  } catch (error) {
    if (error instanceof BackendApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}
