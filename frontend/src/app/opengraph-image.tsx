import { ImageResponse } from "next/og";

import { SITE } from "@/lib/seo";
import { APP_BRAND } from "@/lib/constants";
import { ResearchMark } from "@/components/brand/research-mark";

export const alt = `${SITE.name} — ${SITE.tagline}`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const dynamic = "force-static";

// Lorentzian resonance across the card: baseline 470, apex (930, 150), half width 62.
const x = (i: number) => 500 + i * 10;
const PEAK = `M${Array.from({ length: 71 }, (_, i) => `${x(i)} ${(470 - 320 / (1 + ((x(i) - 930) / 62) ** 2)).toFixed(1)}`).join("L")}`;

const CHANNELS = [
  ["CH1", "规划", "#FFD23F"],
  ["CH2", "研究", "#3DD6FF"],
  ["CH3", "撰写", "#FF6AD5"],
  ["CH4", "审校", "#8CF56F"],
] as const;

/** Share card in the instrument style: ink screen, graticule, signal-orange resonance. */
export default function OpengraphImage() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: "56px 72px",
        position: "relative",
        backgroundColor: "#0B0B0C",
        backgroundImage:
          "linear-gradient(rgba(236,235,230,0.055) 1px, transparent 1px), linear-gradient(90deg, rgba(236,235,230,0.055) 1px, transparent 1px)",
        backgroundSize: "40px 40px",
        color: "#ECEBE6",
        fontFamily: "sans-serif",
      }}
    >
      <svg
        width="1200"
        height="630"
        viewBox="0 0 1200 630"
        style={{ position: "absolute", left: 0, top: 0 }}
      >
        <path d="M0 470H1200" stroke="#36363B" strokeWidth="2" />
        <path d={PEAK} stroke="#FF5A1F" strokeOpacity="0.25" strokeWidth="18" fill="none" />
        <path d={PEAK} stroke="#FF5A1F" strokeWidth="5" fill="none" strokeLinejoin="round" />
        <path d="M916 112H944L930 132Z" fill="#ECEBE6" />
        <path
          d="M930 150V470"
          stroke="#FF5A1F"
          strokeOpacity="0.6"
          strokeWidth="2"
          strokeDasharray="6 8"
        />
      </svg>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <ResearchMark size={52} />
          <span style={{ fontSize: 24, fontWeight: 700, letterSpacing: "0.08em" }}>
            RESEARCH AGENT
          </span>
        </div>
        <span
          style={{
            fontSize: 18,
            fontFamily: "monospace",
            letterSpacing: "0.14em",
            color: "#9B9A95",
          }}
        >
          {APP_BRAND} · FIG.01
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column" }}>
        <span style={{ fontSize: 24, color: "#FF5A1F", letterSpacing: "0.04em" }}>
          {SITE.tagline}
        </span>
        <span style={{ marginTop: 18, fontSize: 48, fontWeight: 700, lineHeight: 1.25 }}>
          一个问题，
        </span>
        <span style={{ fontSize: 48, fontWeight: 700, lineHeight: 1.25 }}>
          交给一支会查证的 AI 研究小组。
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", gap: 22 }}>
          {CHANNELS.map(([ch, name, color]) => (
            <div key={ch} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 22 }}>
              <div style={{ width: 12, height: 12, background: color }} />
              <span style={{ fontFamily: "monospace", color }}>{ch}</span>
              <span style={{ color: "#ECEBE6" }}>{name}</span>
            </div>
          ))}
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            padding: "14px 26px",
            background: "#FF5A1F",
            color: "#0B0B0C",
            fontSize: 22,
            fontWeight: 700,
          }}
        >
          开始研究 →
        </div>
      </div>
    </div>,
    { ...size },
  );
}
