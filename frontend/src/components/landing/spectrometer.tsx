"use client";

import { useEffect, useId, useRef, useState } from "react";

export interface SpectrometerLabels {
  index: string;
  particle: string;
  sphere: string;
  rod: string;
  peak: string;
  shift: string;
  fwhm: string;
  sensitivity: string;
  fom: string;
  axisX: string;
  axisY: string;
  reference: string;
  note: string;
  /** Template with {particle}, {n} and {peak}. */
  plotLabel: string;
}

type ParticleKey = "sphere" | "rod";
interface Band {
  lambda0: number;
  /** nm per refractive index unit */
  sensitivity: number;
  fwhm: number;
  amp: number;
}

// Typical literature magnitudes (illustrative): a ~40 nm sphere and an aspect-ratio-3 rod,
// whose weak transverse band barely moves while the longitudinal band shifts strongly.
const PARTICLES: Record<ParticleKey, Band[]> = {
  sphere: [{ lambda0: 526, sensitivity: 88, fwhm: 62, amp: 1 }],
  rod: [
    { lambda0: 692, sensitivity: 288, fwhm: 84, amp: 1 },
    { lambda0: 518, sensitivity: 28, fwhm: 56, amp: 0.26 },
  ],
};
const N0 = 1.333;
const N_MIN = 1.33;
const N_MAX = 1.43;
const L_MIN = 420;
const L_MAX = 900;

const W = 640;
const H = 280;
const PAD = { left: 46, right: 14, top: 22, bottom: 38 };
const px = (lambda: number) =>
  PAD.left + ((lambda - L_MIN) / (L_MAX - L_MIN)) * (W - PAD.left - PAD.right);
const py = (v: number) => H - PAD.bottom - v * (H - PAD.top - PAD.bottom);

const lorentz = (lambda: number, centre: number, fwhm: number) =>
  1 / (1 + ((lambda - centre) / (fwhm / 2)) ** 2);

function spectrum(bands: Band[], n: number) {
  const points: string[] = [];
  for (let lambda = L_MIN; lambda <= L_MAX; lambda += 3) {
    const v = bands.reduce(
      (sum, b) => sum + b.amp * lorentz(lambda, b.lambda0 + b.sensitivity * (n - N0), b.fwhm),
      0,
    );
    points.push(`${px(lambda).toFixed(1)} ${py(Math.min(v, 1.08)).toFixed(1)}`);
  }
  return `M${points.join("L")}`;
}

const X_TICKS = [450, 500, 550, 600, 650, 700, 750, 800, 850];
const Y_TICKS = [0, 0.25, 0.5, 0.75, 1];

/**
 * Interactive LSPR sketch: the medium's refractive index shifts Lorentzian
 * extinction peaks. Sweeps by itself while visible until the visitor touches a
 * control; static under reduced motion.
 */
export function Spectrometer({ labels }: { labels: SpectrometerLabels }) {
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);
  const touched = useRef(false);
  const [particle, setParticle] = useState<ParticleKey>("rod");
  const [n, setN] = useState(1.36);

  useEffect(() => {
    const el = ref.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let raf = 0;
    let visible = false;
    let origin = 0;
    let last = 0;
    const tick = (now: number) => {
      raf = 0;
      if (touched.current || !visible || document.hidden) return;
      if (!origin) origin = now;
      if (now - last > 33) {
        last = now;
        const phase = ((now - origin) / 7000) * Math.PI * 2;
        setN(Number((N0 + 0.07 * (0.5 - 0.5 * Math.cos(phase))).toFixed(3)));
      }
      raf = requestAnimationFrame(tick);
    };
    const start = () => {
      if (!raf && visible && !touched.current) raf = requestAnimationFrame(tick);
    };
    const observer = new IntersectionObserver(([entry]) => {
      visible = !!entry?.isIntersecting;
      start();
    });
    observer.observe(el);
    document.addEventListener("visibilitychange", start);
    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      document.removeEventListener("visibilitychange", start);
    };
  }, []);

  const stop = () => {
    touched.current = true;
  };

  const bands = PARTICLES[particle];
  const main = bands[0]!;
  const shift = main.sensitivity * (n - N0);
  const peak = main.lambda0 + shift;
  const name = particle === "rod" ? labels.rod : labels.sphere;
  const plotLabel = labels.plotLabel
    .replace("{particle}", name)
    .replace("{n}", n.toFixed(3))
    .replace("{peak}", peak.toFixed(1));

  return (
    <div ref={ref} className="spectro">
      <div className="spectro-screen">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={plotLabel}>
          <g className="spectro-grid">
            {X_TICKS.map((l) => (
              <line key={l} x1={px(l)} x2={px(l)} y1={PAD.top} y2={H - PAD.bottom} />
            ))}
            {Y_TICKS.map((v) => (
              <line key={v} x1={PAD.left} x2={W - PAD.right} y1={py(v)} y2={py(v)} />
            ))}
          </g>
          <g className="spectro-axis">
            <line x1={PAD.left} x2={W - PAD.right} y1={py(0)} y2={py(0)} />
            <line x1={PAD.left} x2={PAD.left} y1={PAD.top} y2={py(0)} />
            {X_TICKS.filter((l) => l % 100 === 0).map((l) => (
              <text key={l} x={px(l)} y={H - PAD.bottom + 16} textAnchor="middle">
                {l}
              </text>
            ))}
            <text x={W - PAD.right} y={H - 6} textAnchor="end">
              {labels.axisX}
            </text>
            <text x={PAD.left - 8} y={py(1) + 4} textAnchor="end">
              1.0
            </text>
            <text x={PAD.left - 8} y={py(0) + 4} textAnchor="end">
              0
            </text>
          </g>
          <path className="spectro-ref" d={spectrum(bands, N0)} />
          <path className="spectro-curve" d={spectrum(bands, n)} />
          <g className="spectro-marker" transform={`translate(${px(peak).toFixed(1)} 0)`}>
            <line y1={py(1) + 6} y2={py(0)} />
            <path d={`M-5 ${py(1) - 9}H5L0 ${py(1) - 2}Z`} />
            <text x={8} y={py(1) - 2}>
              {peak.toFixed(1)} nm
            </text>
          </g>
        </svg>
        <div
          className="spectro-band"
          aria-hidden
          style={{
            marginLeft: `${(PAD.left / W) * 100}%`,
            marginRight: `${(PAD.right / W) * 100}%`,
          }}
        />
        <p className="spectro-legend" aria-hidden>
          <span className="is-ref">{labels.reference}</span>
          <span className="is-cur">n = {n.toFixed(3)}</span>
          <span>{labels.axisY}</span>
        </p>
      </div>

      <div className="spectro-panel">
        <fieldset className="spectro-switch" onChange={stop}>
          <legend className="mono-label">{labels.particle}</legend>
          {(["sphere", "rod"] as const).map((key) => (
            <label key={key}>
              <input
                type="radio"
                name={`${id}-particle`}
                value={key}
                checked={particle === key}
                onChange={() => setParticle(key)}
              />
              <span>{key === "rod" ? labels.rod : labels.sphere}</span>
            </label>
          ))}
        </fieldset>

        <div className="spectro-slider">
          <label className="mono-label" htmlFor={`${id}-n`}>
            {labels.index}
          </label>
          <output htmlFor={`${id}-n`}>{n.toFixed(3)}</output>
        </div>
        <input
          id={`${id}-n`}
          type="range"
          min={N_MIN}
          max={N_MAX}
          step={0.001}
          value={n}
          aria-valuetext={`n = ${n.toFixed(3)}`}
          onPointerDown={stop}
          onKeyDown={stop}
          onChange={(e) => {
            stop();
            setN(Number(e.target.value));
          }}
          style={{ "--fill": `${((n - N_MIN) / (N_MAX - N_MIN)) * 100}%` } as React.CSSProperties}
        />

        <dl className="spectro-readout">
          <div>
            <dt>{labels.peak}</dt>
            <dd>
              {peak.toFixed(1)}
              <small>nm</small>
            </dd>
          </div>
          <div>
            <dt>{labels.shift}</dt>
            <dd className={shift > 0.05 ? "is-hot" : undefined}>
              {shift >= 0 ? "+" : "−"}
              {Math.abs(shift).toFixed(1)}
              <small>nm</small>
            </dd>
          </div>
          <div>
            <dt>{labels.sensitivity}</dt>
            <dd>
              {main.sensitivity}
              <small>nm/RIU</small>
            </dd>
          </div>
          <div>
            <dt>{labels.fwhm}</dt>
            <dd>
              {main.fwhm}
              <small>nm</small>
            </dd>
          </div>
          <div>
            <dt>{labels.fom}</dt>
            <dd>{(main.sensitivity / main.fwhm).toFixed(1)}</dd>
          </div>
        </dl>
        <p className="spectro-note">{labels.note}</p>
      </div>
    </div>
  );
}
