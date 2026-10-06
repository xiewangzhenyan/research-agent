"use client";

import { useEffect, useRef, useState } from "react";

import { WaveField, type Probe } from "./wave-field";

export interface HeroFieldLabels {
  figure: string;
  hint: string;
  hintTouch: string;
  probe: string;
  amplitude: string;
  steps: string;
  still: string;
}

type Mode = "live" | "still" | "fallback";

const INTERACTIVE = "a,button,input,select,textarea,label,[role=button]";
const format = (v: number, digits = 3) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(digits);

/**
 * Hero instrument screen: the WebGL wave field plus its HUD. The field pauses
 * off screen and in background tabs; with reduced motion it renders one
 * developed frame and ignores the pointer; without WebGL2 a static gradient
 * stands in. Purely decorative for assistive tech.
 */
export function HeroField({ labels }: { labels: HeroFieldLabels }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const crossRef = useRef<HTMLDivElement>(null);
  const readRef = useRef<HTMLSpanElement>(null);
  const stepRef = useRef<HTMLSpanElement>(null);
  const [mode, setMode] = useState<Mode>("live");
  const [touch, setTouch] = useState(false);

  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setTouch(window.matchMedia("(pointer: coarse)").matches);
    const narrow = wrap.clientWidth < 720;
    const field = WaveField.create(canvas, {
      cells: narrow ? 210 : 330,
      dim: narrow ? 0.55 : 0.22,
    });
    if (!field) {
      setMode("fallback");
      return;
    }

    let raf = 0;
    let frame = 0;
    let steps = 0;
    let visible = true;
    let probe: Probe | null = null;
    const fit = () => {
      const rect = wrap.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      field.resize(rect.width, rect.height);
    };
    fit();
    // Pre-roll so the first painted frame already shows a developed field.
    field.advance(reduced ? 900 : 420);
    steps += reduced ? 900 : 420;
    field.draw(canvas.width, canvas.height);

    if (reduced) {
      setMode("still");
      const resize = new ResizeObserver(() => {
        fit();
        field.advance(600);
        field.draw(canvas.width, canvas.height);
      });
      resize.observe(wrap);
      return () => {
        resize.disconnect();
        field.dispose();
      };
    }

    const loop = () => {
      raf = 0;
      if (!visible || document.hidden) return;
      field.advance(3);
      steps += 3;
      field.draw(canvas.width, canvas.height);
      frame += 1;
      if (frame % 8 === 0) {
        if (stepRef.current) stepRef.current.textContent = String(steps).padStart(7, "0");
        if (probe && readRef.current) {
          const v = field.sample(probe.x, probe.y);
          if (v !== null) readRef.current.textContent = format(v);
        }
      }
      raf = requestAnimationFrame(loop);
    };
    const start = () => {
      if (!raf && visible && !document.hidden) raf = requestAnimationFrame(loop);
    };

    const toField = (event: PointerEvent): Probe | null => {
      const rect = wrap.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width;
      const y = (event.clientY - rect.top) / rect.height;
      if (x < 0 || x > 1 || y < 0 || y > 1) return null;
      return { x, y: 1 - y };
    };
    const onMove = (event: PointerEvent) => {
      if (event.pointerType === "touch") return;
      probe = toField(event);
      field.setProbe(probe);
      const cross = crossRef.current;
      if (!cross) return;
      cross.dataset.active = probe ? "true" : "false";
      if (probe) {
        const rect = wrap.getBoundingClientRect();
        cross.style.transform = `translate3d(${probe.x * rect.width}px, ${(1 - probe.y) * rect.height}px, 0)`;
        const coords = cross.querySelector("[data-coords]");
        if (coords) coords.textContent = `x ${probe.x.toFixed(3)}  y ${probe.y.toFixed(3)}`;
      }
    };
    const onDown = (event: PointerEvent) => {
      if ((event.target as Element | null)?.closest(INTERACTIVE)) return;
      const at = toField(event);
      if (at) field.excite(at.x, at.y);
    };

    const intersection = new IntersectionObserver(([entry]) => {
      visible = !!entry?.isIntersecting;
      start();
    });
    intersection.observe(wrap);
    const resize = new ResizeObserver(() => {
      fit();
      field.draw(canvas.width, canvas.height);
    });
    resize.observe(wrap);
    const section = wrap.parentElement ?? wrap;
    window.addEventListener("pointermove", onMove, { passive: true });
    section.addEventListener("pointerdown", onDown);
    document.addEventListener("visibilitychange", start);
    start();

    return () => {
      cancelAnimationFrame(raf);
      intersection.disconnect();
      resize.disconnect();
      window.removeEventListener("pointermove", onMove);
      section.removeEventListener("pointerdown", onDown);
      document.removeEventListener("visibilitychange", start);
      field.dispose();
    };
  }, []);

  return (
    <div ref={wrapRef} className="field" data-mode={mode} aria-hidden>
      <canvas ref={canvasRef} className="field-canvas" />
      <div className="field-veil" />
      <div className="field-graticule" />
      <div ref={crossRef} className="field-cross" data-active="false">
        <span>
          <b>{labels.probe}</b>
          <span data-coords />
        </span>
      </div>
      <div className="field-hud">
        <p className="field-fig">{labels.figure}</p>
        <p className="field-hint">
          {mode !== "live" ? labels.still : touch ? labels.hintTouch : labels.hint}
        </p>
        <dl className="field-readout">
          <div>
            <dt>{labels.amplitude}</dt>
            <dd>
              <span ref={readRef}>{format(0)}</span>
            </dd>
          </div>
          <div>
            <dt>{labels.steps}</dt>
            <dd>
              <span ref={stepRef}>0000000</span>
            </dd>
          </div>
        </dl>
        <div className="field-colorbar">
          <i />
          <span>0</span>
          <span>|ψ|</span>
          <span>max</span>
        </div>
      </div>
    </div>
  );
}
