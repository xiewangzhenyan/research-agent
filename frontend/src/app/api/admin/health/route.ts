import { NextRequest, NextResponse } from "next/server";
import { requireAdmin } from "@/lib/admin-auth";
import { backendFetch, BackendApiError } from "@/lib/server-api";
export async function GET(request: NextRequest) {
  const auth = await requireAdmin(request);
  if ("error" in auth) return auth.error;
  try {
    return NextResponse.json(await backendFetch("/api/v1/health/ready", { cache: "no-store" }));
  } catch (error) {
    if (error instanceof BackendApiError && error.status === 503) {
      // Preserve dependency states for the administrator when readiness fails.
      return NextResponse.json(error.data);
    }
    return NextResponse.json({ detail: "Health check failed" }, { status: 502 });
  }
}
