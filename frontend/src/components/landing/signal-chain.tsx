import { getTranslations } from "next-intl/server";

import { Reveal } from "@/components/motion/reveal";

const ROLES = [
  { key: "plan", tag: "PLAN" },
  { key: "research", tag: "RSRCH" },
  { key: "write", tag: "WRITE" },
  { key: "review", tag: "REVIEW" },
] as const;

type Role = (typeof ROLES)[number]["key"];

// One period of each channel's trace, 60 units wide on a 40-unit-high screen. The
// strip repeats it eight times and scrolls by half, so the loop is seamless.
const PERIOD: Record<Role, (x: number) => string> = {
  // Square wave: the plan breaks a question into discrete steps.
  plan: (x) => `L${x} 30L${x} 10L${x + 30} 10L${x + 30} 30`,
  // Sparse spikes: retrieval hits.
  research: (x) =>
    `L${x + 8} 30L${x + 11} 6L${x + 14} 34L${x + 17} 26L${x + 20} 30L${x + 38} 30L${x + 41} 16L${x + 44} 30`,
  // Smooth carrier: the draft.
  write: (x) =>
    Array.from({ length: 13 }, (_, i) => {
      const px = x + i * 5;
      return `L${px} ${(20 - 11 * Math.sin((i / 12) * Math.PI * 2)).toFixed(1)}`;
    }).join(""),
  // Gate pulses: checks passed.
  review: (x) => `L${x + 26} 30L${x + 26} 12L${x + 34} 12L${x + 34} 30`,
};

const trace = (role: Role) =>
  `M0 30${Array.from({ length: 8 }, (_, i) => PERIOD[role](i * 60)).join("")}L480 30`;

/** The four roles drawn as a scope's signal chain: input → CH1…CH4 → output. */
export async function SignalChain() {
  const t = await getTranslations("landing.workflow");
  return (
    <Reveal className="chain">
      <div className="chain-io reveal-item">
        <span className="mono-label">IN</span>
        <strong>{t("input")}</strong>
      </div>
      <ol className="chain-track">
        {ROLES.map((role, i) => (
          <li
            key={role.key}
            className={`chain-ch role-${role.key} reveal-item`}
            style={{ "--i": i + 1 } as React.CSSProperties}
          >
            <header>
              <span>CH{i + 1}</span>
              <span>{role.tag}</span>
            </header>
            <div className="chain-screen" aria-hidden>
              <svg viewBox="0 0 480 40" preserveAspectRatio="none">
                <path d={trace(role.key)} />
              </svg>
            </div>
            <h3>{t(`${role.key}Title`)}</h3>
            <p>{t(`${role.key}Desc`)}</p>
            <span className="chain-out">→ {t(`${role.key}Output`)}</span>
          </li>
        ))}
      </ol>
      <div className="chain-io is-out reveal-item" style={{ "--i": 5 } as React.CSSProperties}>
        <span className="mono-label">OUT</span>
        <strong>{t("output")}</strong>
      </div>
      <p className="chain-loop reveal-item" style={{ "--i": 6 } as React.CSSProperties}>
        <span aria-hidden>↺</span>
        {t("loop")}
      </p>
    </Reveal>
  );
}
