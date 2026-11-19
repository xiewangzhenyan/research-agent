export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ status: "ready" }, { headers: { "Cache-Control": "no-store" } });
}
