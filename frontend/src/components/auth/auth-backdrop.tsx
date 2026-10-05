/** Decorative pipeline lines and pulsing nodes behind the auth pages. */
const LINES = [
  { d: "M-40 640 C 220 560 360 700 620 600 S 980 420 1480 500", role: "write" },
  { d: "M-40 300 C 260 240 420 380 700 320 S 1100 160 1480 220", role: "research" },
  { d: "M120 960 C 300 760 560 820 760 700 S 1120 640 1480 760", role: "plan" },
] as const;

const NODES = [
  { cx: 620, cy: 600, role: "write" },
  { cx: 1035, cy: 455, role: "write" },
  { cx: 700, cy: 320, role: "research" },
  { cx: 290, cy: 268, role: "research" },
  { cx: 760, cy: 700, role: "plan" },
  { cx: 1210, cy: 690, role: "review" },
] as const;

export function AuthBackdrop() {
  return (
    <div className="auth-bg" aria-hidden>
      <svg viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice">
        {LINES.map((line) => (
          <path
            key={line.d}
            d={line.d}
            className={`auth-line role-${line.role}`}
            fill="none"
            strokeWidth="1.2"
          />
        ))}
        {NODES.map((node, i) => (
          <circle
            key={`${node.cx}-${node.cy}`}
            cx={node.cx}
            cy={node.cy}
            r="4"
            className={`auth-node role-${node.role}`}
            style={{ animationDelay: `${i * 0.7}s` }}
          />
        ))}
      </svg>
    </div>
  );
}
