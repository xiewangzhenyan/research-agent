import { cn } from "@/lib/utils";

interface ResearchMarkProps {
  size?: number;
  className?: string;
  /** Draw the resonance curve in and let the peak node breathe (empty/loading states). */
  animated?: boolean;
}

/** LSPRAI resonance peak and connected knowledge nodes; no external assets. */
export function ResearchMark({ size = 32, className, animated = false }: ResearchMarkProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      className={cn(animated && "research-mark-animated", className)}
      aria-hidden="true"
      focusable="false"
    >
      <rect
        x="1"
        y="1"
        width="62"
        height="62"
        rx="17"
        fill="#0D2421"
        stroke="#326456"
        strokeWidth="2"
      />
      <path
        d="M12 47C25 47 26 34 35 34S44 47 52 47"
        stroke="#4C9A82"
        strokeWidth="2.5"
        strokeLinecap="round"
        pathLength={1}
        className="mark-curve"
      />
      <path
        d="M12 41C23 41 22 19 32 19S41 41 52 41"
        stroke="#A3F0CE"
        strokeWidth="4.5"
        strokeLinecap="round"
        pathLength={1}
        className="mark-curve"
      />
      <circle cx="12" cy="41" r="3.5" fill="#A3F0CE" />
      <circle cx="52" cy="41" r="3.5" fill="#A3F0CE" />
      <circle cx="32" cy="19" r="5" fill="#D9FFED" className="mark-peak" />
      <circle cx="32" cy="19" r="2" fill="#0D2421" />
    </svg>
  );
}
