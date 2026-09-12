import { ImageResponse } from "next/og";
import { ResearchMark } from "@/components/brand/research-mark";

/** Shared LSPRAI mark, rendered as a compact PNG for browser tabs. */
export const size = { width: 32, height: 32 };
export const contentType = "image/png";
export const dynamic = "force-static";

export default function Icon() {
  return new ImageResponse(<ResearchMark size={32} />, { ...size });
}
