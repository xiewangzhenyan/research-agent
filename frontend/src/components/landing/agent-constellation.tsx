"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import {
  FileText,
  ListTree,
  MessageCircleQuestion,
  PenLine,
  Search,
  ShieldCheck,
} from "lucide-react";

import { cn } from "@/lib/utils";

const ROLES = [
  { key: "plan", x: 50, y: 12, icon: ListTree },
  { key: "research", x: 88, y: 50, icon: Search },
  { key: "write", x: 50, y: 88, icon: PenLine },
  { key: "review", x: 12, y: 50, icon: ShieldCheck },
] as const;

/** Question → plan → research → write → review → back to the answer, on one ring. */
const LOOP = "M50 50 L50 12 A38 38 0 0 1 88 50 A38 38 0 0 1 50 88 A38 38 0 0 1 12 50 L50 50";
const LINKS = [
  { d: "M50 12 A38 38 0 0 1 88 50", role: "plan" },
  { d: "M88 50 A38 38 0 0 1 50 88", role: "research" },
  { d: "M50 88 A38 38 0 0 1 12 50", role: "write" },
  { d: "M12 50 L50 50", role: "review" },
] as const;

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Plays only while on screen and the tab is visible; static under reduced motion. */
function usePlayback(ref: React.RefObject<HTMLElement | null>) {
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion()) return;
    let inView = false;
    const sync = () => setPlaying(inView && document.visibilityState === "visible");
    const observer = new IntersectionObserver(([entry]) => {
      inView = !!entry?.isIntersecting;
      sync();
    });
    observer.observe(el);
    document.addEventListener("visibilitychange", sync);
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", sync);
    };
  }, [ref]);
  return playing;
}

function HeroAnswerCard() {
  const t = useTranslations("landing.constellation");
  const text = t("answerText");
  const cut = Math.max(text.search(/[；;]/), 0) || Math.floor(text.length / 2);
  // Server HTML carries the full sentence; the typewriter only runs client-side.
  const [typed, setTyped] = useState(text.length);

  useEffect(() => {
    if (prefersReducedMotion()) return;
    setTyped(0);
    let interval: ReturnType<typeof setInterval> | undefined;
    const start = setTimeout(() => {
      interval = setInterval(() => {
        setTyped((n) => {
          if (n + 1 >= text.length && interval) clearInterval(interval);
          return Math.min(n + 1, text.length);
        });
      }, 28);
    }, 1200);
    return () => {
      clearTimeout(start);
      if (interval) clearInterval(interval);
    };
  }, [text]);

  const done = typed >= text.length;
  return (
    <div className="answer-card" aria-hidden>
      <header>
        <span className="text-foreground inline-flex items-center gap-2 font-medium">
          <span className="bg-brand inline-block h-1.5 w-1.5 rounded-full" />
          {t("answerTitle")}
        </span>
        <span className="rounded-full border px-2 py-0.5">{t("answerSample")}</span>
      </header>
      <p>
        {text.slice(0, Math.min(typed, cut))}
        {typed >= cut && <span className="citation-chip pop-in">1</span>}
        {typed > cut && text.slice(cut, typed)}
        {done ? <span className="citation-chip pop-in">2</span> : <span className="answer-caret" />}
      </p>
      <div className={cn("answer-sources", !done && "invisible")}>
        <span>
          <FileText size={11} />1 · {t("sourceOne")}
        </span>
        <span>
          <FileText size={11} />2 · {t("sourceTwo")}
        </span>
      </div>
    </div>
  );
}

export function AgentConstellation() {
  const t = useTranslations("landing.constellation");
  const ref = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const playing = usePlayback(ref);
  const [active, setActive] = useState(-1);
  const uid = useId().replace(/:/g, "");

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    if (playing) svg.unpauseAnimations();
    else svg.pauseAnimations();
    if (!playing) return;
    const timer = setInterval(() => setActive((i) => (i + 1) % ROLES.length), 1800);
    return () => clearInterval(timer);
  }, [playing]);

  return (
    <div ref={ref} className={cn("hero-visual", !playing && "is-paused")}>
      <div className="constellation" role="img" aria-label={t("label")}>
        <svg ref={svgRef} viewBox="0 0 100 100" aria-hidden>
          <defs>
            <radialGradient id={`${uid}-spark`}>
              <stop offset="0%" style={{ stopColor: "var(--color-foreground)" }} />
              <stop offset="100%" style={{ stopColor: "var(--color-brand)" }} stopOpacity={0} />
            </radialGradient>
          </defs>
          <g className="constellation-orbit">
            <circle cx="50" cy="50" r="47" className="constellation-ring" strokeDasharray="1 3" />
          </g>
          <circle cx="50" cy="50" r="38" className="constellation-ring" />
          <circle cx="50" cy="50" r="26" className="constellation-ring" strokeDasharray="0.6 2" />
          {ROLES.map((role) => (
            <line
              key={role.key}
              x1="50"
              y1="50"
              x2={role.x}
              y2={role.y}
              className="constellation-spoke"
            />
          ))}
          {LINKS.map((link, i) => (
            <path
              key={link.d}
              d={link.d}
              pathLength={1}
              className={cn("constellation-link", `role-${link.role}`)}
              style={{ stroke: "var(--role)", animationDelay: `${300 + i * 220}ms` }}
            />
          ))}
          {[0, 1, 2].map((i) => (
            <circle key={i} r="1.6" fill={`url(#${uid}-spark)`}>
              <animateMotion
                dur="7.2s"
                begin={`${-i * 2.4}s`}
                repeatCount="indefinite"
                path={LOOP}
              />
            </circle>
          ))}
        </svg>

        <div className="constellation-core">
          <MessageCircleQuestion size={30} strokeWidth={1.6} className="text-brand" />
          <span>{t("core")}</span>
        </div>

        {ROLES.map((role, i) => (
          <div
            key={role.key}
            className={cn("constellation-node", `role-${role.key}`)}
            data-active={active === i}
            style={{ left: `${role.x}%`, top: `${role.y}%`, "--i": i } as React.CSSProperties}
          >
            <span className="icon-chip">
              <role.icon size={15} strokeWidth={2} />
            </span>
            <span>
              <strong>{t(`${role.key}Name`)}</strong>
              <small>{t(`${role.key}Desc`)}</small>
            </span>
          </div>
        ))}
      </div>
      <HeroAnswerCard />
    </div>
  );
}
