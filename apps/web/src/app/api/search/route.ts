import { NextResponse } from "next/server";
import { runSearch } from "@/lib/search";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const q = (searchParams.get("q") ?? "").slice(0, 80);
  const result = await runSearch(q);
  return NextResponse.json(result, {
    headers: { "Cache-Control": "private, max-age=30" },
  });
}
