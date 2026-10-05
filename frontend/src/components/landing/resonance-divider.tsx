"use client";

import { useId } from "react";

import { Reveal } from "@/components/motion/reveal";
import { cn } from "@/lib/utils";

/** The LSPR resonance peak from the logo, drawn across the page as a section break. */
export function ResonanceDivider({ className }: { className?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <Reveal className={cn("resonance-divider", className)}>
      <svg viewBox="0 0 1200 80" preserveAspectRatio="none" aria-hidden className="h-full w-full">
        <defs>
          <linearGradient id={`${id}-g`} x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" style={{ stopColor: "var(--color-role-write)" }} stopOpacity={0} />
            <stop offset="34%" style={{ stopColor: "var(--color-role-write)" }} />
            <stop offset="50%" style={{ stopColor: "var(--color-role-research)" }} />
            <stop offset="66%" style={{ stopColor: "var(--color-role-plan)" }} />
            <stop offset="100%" style={{ stopColor: "var(--color-role-plan)" }} stopOpacity={0} />
          </linearGradient>
        </defs>
        <path
          d="M0 70 C 420 70 520 68 610 52 C 660 44 700 64 770 68 C 880 72 1000 72 1200 72"
          pathLength={1}
          stroke={`url(#${id}-g)`}
          strokeOpacity={0.35}
        />
        <path
          d="M0 64 C 380 64 470 62 540 46 C 575 38 588 10 600 10 C 612 10 625 38 660 46 C 730 62 820 64 1200 64"
          pathLength={1}
          stroke={`url(#${id}-g)`}
        />
      </svg>
    </Reveal>
  );
}
