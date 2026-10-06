import { cn } from "@/lib/utils";

interface ResearchMarkProps {
  size?: number;
  className?: string;
  /** Draw the peak in and blink the marker (empty and loading states). */
  animated?: boolean;
}

// Lorentzian line shape sampled at integer x: baseline 45.3, apex (32, 15), half width 5.2.
const PEAK =
  "M10 45.3L13 44.8L16 43.9L18 43.1L20 41.9L22 40.2L24 37.5L25 35.6L26 33.3L27 30.4L28 26.9L29 23L30 19.1L31 16.1L32 15L33 16.1L34 19.1L35 23L36 26.9L37 30.4L38 33.3L39 35.6L40 37.5L42 40.2L44 41.9L46 43.1L48 43.9L51 44.8L54 45.3";

/** LSPRAI mark: a resonance peak on an instrument screen, with a measurement marker. */
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
      <rect width="64" height="64" rx="4" fill="#0B0B0C" />
      <path d="M21.5 4V60M42.5 4V60M4 21.5H60M4 32.5H60" stroke="#1C1C20" strokeWidth="1" />
      <rect
        x="0.75"
        y="0.75"
        width="62.5"
        height="62.5"
        rx="3.5"
        stroke="#2A2A2F"
        strokeWidth="1.5"
      />
      <path d="M10 52.5H54M16 52.5V56M32 52.5V56M48 52.5V56" stroke="#4A4A50" strokeWidth="2" />
      <path
        d={PEAK}
        stroke="#FF5A1F"
        strokeWidth="4.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        pathLength={1}
        className="mark-curve"
      />
      <path d="M27.5 5.5H36.5L32 10.5Z" fill="#EDEDEA" className="mark-peak" />
    </svg>
  );
}
