/** LSPRAI resonance peak and connected knowledge nodes; no motion or external assets. */
export function ResearchMark({ size = 32, className }: { size?: number; className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      className={className}
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
      />
      <path
        d="M12 41C23 41 22 19 32 19S41 41 52 41"
        stroke="#A3F0CE"
        strokeWidth="4.5"
        strokeLinecap="round"
      />
      <circle cx="12" cy="41" r="3.5" fill="#A3F0CE" />
      <circle cx="52" cy="41" r="3.5" fill="#A3F0CE" />
      <circle cx="32" cy="19" r="5" fill="#D9FFED" />
      <circle cx="32" cy="19" r="2" fill="#0D2421" />
    </svg>
  );
}
