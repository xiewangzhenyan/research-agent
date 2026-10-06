/** Graticule and four faint channel traces drifting along the bottom of the auth pages. */
const TRACES = [
  { role: "plan", y: 70, d: (x: number) => `L${x} 70L${x} 58L${x + 40} 58L${x + 40} 70` },
  {
    role: "research",
    y: 100,
    d: (x: number) => `L${x + 18} 100L${x + 22} 80L${x + 26} 108L${x + 30} 100`,
  },
  {
    role: "write",
    y: 130,
    d: (x: number) =>
      Array.from(
        { length: 9 },
        (_, i) => `L${x + i * 10} ${(130 - 9 * Math.sin((i / 8) * Math.PI * 2)).toFixed(1)}`,
      ).join(""),
  },
  {
    role: "review",
    y: 160,
    d: (x: number) => `L${x + 52} 160L${x + 52} 146L${x + 60} 146L${x + 60} 160`,
  },
] as const;

const path = (trace: (typeof TRACES)[number]) =>
  `M0 ${trace.y}${Array.from({ length: 36 }, (_, i) => trace.d(i * 80)).join("")}L2880 ${trace.y}`;

export function AuthBackdrop() {
  return (
    <div className="auth-bg" aria-hidden>
      <svg viewBox="0 0 2880 200" preserveAspectRatio="none">
        {TRACES.map((trace) => (
          <path key={trace.role} d={path(trace)} className={`auth-line role-${trace.role}`} />
        ))}
      </svg>
    </div>
  );
}
