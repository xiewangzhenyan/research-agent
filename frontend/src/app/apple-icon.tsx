import { ImageResponse } from "next/og";

import { ResearchMark } from "@/components/brand/research-mark";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";
export const dynamic = "force-static";

export default function AppleIcon() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#0D2421",
      }}
    >
      <ResearchMark size={132} />
    </div>,
    { ...size },
  );
}
