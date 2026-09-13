import { forwardProjectHeaders } from "@/lib/server-api";
import { NextRequest, NextResponse } from "next/server";
import { backendFetch, BackendApiError } from "@/lib/server-api";

export async function GET(request: NextRequest) {
  try {
    const accessToken = request.cookies.get("access_token")?.value;

    if (!accessToken) {
      return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }

    const qs = request.nextUrl.searchParams.toString();

    const data = await backendFetch(`/api/v1/conversations${qs ? `?${qs}` : ""}`, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
        ...forwardProjectHeaders(request),
      },
    });

    return NextResponse.json(data, { headers: { "Cache-Control": "private, no-store" } });
  } catch (error) {
    if (error instanceof BackendApiError) {
      return NextResponse.json(
        { detail: error.message || "Failed to fetch conversations" },
        { status: error.status },
      );
    }
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const accessToken = request.cookies.get("access_token")?.value;

    if (!accessToken) {
      return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }

    const body = await request.json();

    const data = await backendFetch("/api/v1/conversations", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        ...forwardProjectHeaders(request),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    return NextResponse.json(data, { status: 201 });
  } catch (error) {
    if (error instanceof BackendApiError) {
      return NextResponse.json(
        { detail: error.message || "Failed to create conversation" },
        { status: error.status },
      );
    }
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}
