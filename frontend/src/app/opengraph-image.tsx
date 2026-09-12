import { ImageResponse } from "next/og";

import { SITE } from "@/lib/seo";
import { APP_BRAND } from "@/lib/constants";
import { ResearchMark } from "@/components/brand/research-mark";

export const alt = `${SITE.name} — ${SITE.tagline}`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const dynamic = "force-static";

/** Share card using the same LSPRAI mark and mint palette as the workspace. */
export default function OpengraphImage() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: "64px 80px",
        backgroundColor: "#0D2421",
        backgroundImage:
          "radial-gradient(ellipse 80% 60% at 80% 0%, rgba(163,240,206,0.18), transparent 60%)",
        color: "#F2F1EB",
        fontFamily: "sans-serif",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <ResearchMark size={48} />
          <span style={{ fontSize: 26, fontWeight: 700, letterSpacing: "-0.01em" }}>
            {APP_BRAND}
          </span>
        </div>
        <span
          style={{
            fontSize: 18,
            opacity: 0.6,
            fontFamily: "monospace",
            textTransform: "uppercase",
            letterSpacing: "0.1em",
          }}
        >
          {SITE.tagline}
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column" }}>
        <div
          style={{
            fontSize: 100,
            fontWeight: 800,
            lineHeight: 1.0,
            letterSpacing: "-0.035em",
            display: "flex",
            flexWrap: "wrap",
          }}
        >
          <span style={{ color: "#A3F0CE" }}>{SITE.name}</span>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 28, opacity: 0.7, maxWidth: 720, lineHeight: 1.4 }}>
          {SITE.description}
        </span>
        <div
          style={{
            fontSize: 22,
            fontWeight: 600,
            padding: "14px 28px",
            borderRadius: 9999,
            background: "#F2F1EB",
            color: "#0D2421",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          开始探索 →
        </div>
      </div>
    </div>,
    { ...size },
  );
}
