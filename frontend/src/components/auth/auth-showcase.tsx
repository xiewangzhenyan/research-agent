"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { ArrowRight, Check, FileText, History, Pause, Play } from "lucide-react";

import { cn } from "@/lib/utils";

const SLIDES = ["Roles", "Retrieval", "Citation", "Durable"] as const;
type Slide = (typeof SLIDES)[number];
const INTERVAL_MS = 5200;

function RolesFigure() {
  const t = useTranslations("auth.shell");
  const roles = [
    ["plan", "roleShortPlan"],
    ["research", "roleShortResearch"],
    ["write", "roleShortWrite"],
    ["review", "roleShortReview"],
  ] as const;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {roles.map(([role, key], i) => (
        <span key={role} className="flex items-center gap-1.5">
          <span className={cn("role-pill step-reveal", `role-${role}`)} style={{ animationDelay: `${i * 120}ms` }}>
            {t(key)}
          </span>
          {i < roles.length - 1 && <ArrowRight size={12} className="text-subtle" aria-hidden />}
        </span>
      ))}
    </div>
  );
}

function RetrievalFigure() {
  const t = useTranslations("auth.shell");
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 text-xs">
      <div className="space-y-1.5">
        <span className="role-pill role-research step-reveal">{t("retrievalKeyword")}</span>
        <span className="role-pill role-plan step-reveal block w-fit" style={{ animationDelay: "120ms" }}>
          {t("retrievalVector")}
        </span>
      </div>
      <ArrowRight size={14} className="text-subtle" aria-hidden />
      <div className="space-y-1.5">
        <span className="role-pill role-review step-reveal" style={{ animationDelay: "240ms" }}>
          {t("retrievalRerank")}
        </span>
        <span className="role-pill role-write step-reveal block w-fit" style={{ animationDelay: "360ms" }}>
          {t("retrievalTop")}
        </span>
      </div>
    </div>
  );
}

function CitationFigure() {
  const t = useTranslations("auth.shell");
  return (
    <div className="space-y-2 text-xs">
      <p className="step-reveal">
        {t("citationAnswer")}
        <span className="citation-chip">1</span>
      </p>
      <p
        className="text-muted-foreground step-reveal flex items-center gap-1.5"
        style={{ animationDelay: "160ms" }}
      >
        <FileText size={12} className="text-brand" aria-hidden />
        {t("citationSource")}
      </p>
    </div>
  );
}

function DurableFigure() {
  const t = useTranslations("auth.shell");
  const steps = ["durableQueued", "durableRunning", "durableWaiting", "durableResumed", "durableDone"] as const;
  return (
    <ol className="flex flex-wrap items-center gap-1.5 text-xs">
      {steps.map((key, i) => (
        <li
          key={key}
          className="step-reveal flex items-center gap-1.5"
          style={{ animationDelay: `${i * 110}ms` }}
        >
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2 py-0.5",
              i === steps.length - 1 && "border-brand/40 text-brand",
            )}
          >
            {key === "durableResumed" && <History size={11} aria-hidden />}
            {key === "durableDone" && <Check size={11} aria-hidden />}
            {t(key)}
          </span>
          {i < steps.length - 1 && <span className="bg-border h-px w-2" aria-hidden />}
        </li>
      ))}
    </ol>
  );
}

const FIGURES: Record<Slide, () => React.JSX.Element> = {
  Roles: RolesFigure,
  Retrieval: RetrievalFigure,
  Citation: CitationFigure,
  Durable: DurableFigure,
};

/** Capability carousel beside the sign-in form (structure follows WeKnora's login page). */
export function AuthShowcase() {
  const t = useTranslations("auth.shell");
  const ref = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);
  // Hover/focus pause the rotation (WAI-ARIA carousel pattern); the button stops it for good.
  const [hovering, setHovering] = useState(false);
  const [stopped, setStopped] = useState(false);

  const next = useCallback(() => setIndex((i) => (i + 1) % SLIDES.length), []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const pause = () => setHovering(true);
    const resume = (event: Event) => {
      if (event instanceof FocusEvent && el.contains(event.relatedTarget as Node)) return;
      setHovering(false);
    };
    el.addEventListener("pointerenter", pause);
    el.addEventListener("pointerleave", resume);
    el.addEventListener("focusin", pause);
    el.addEventListener("focusout", resume);
    return () => {
      el.removeEventListener("pointerenter", pause);
      el.removeEventListener("pointerleave", resume);
      el.removeEventListener("focusin", pause);
      el.removeEventListener("focusout", resume);
    };
  }, []);

  useEffect(() => {
    if (hovering || stopped || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = setInterval(next, INTERVAL_MS);
    return () => clearInterval(timer);
  }, [hovering, stopped, next]);

  return (
    <div
      ref={ref}
      className="auth-carousel"
      role="region"
      aria-roledescription="carousel"
      aria-label={t("slidesLabel")}
    >
      {SLIDES.map((slide, i) => {
        const Figure = FIGURES[slide];
        return (
          <div
            key={slide}
            className={cn("auth-slide", i === index && "is-active")}
            aria-hidden={i !== index}
          >
            <h3>{t(`slide${slide}Title`)}</h3>
            <p>{t(`slide${slide}Desc`)}</p>
            {i === index && (
              <div className="auth-slide-figure">
                <Figure />
              </div>
            )}
          </div>
        );
      })}
      <div className="auth-dots items-center">
        <button
          type="button"
          className="text-muted-foreground hover:text-foreground mr-1 grid h-5 w-5 place-items-center rounded-full"
          aria-label={stopped ? t("playSlides") : t("pauseSlides")}
          onClick={() => setStopped((v) => !v)}
        >
          {stopped ? <Play size={11} /> : <Pause size={11} />}
        </button>
        {SLIDES.map((slide, i) => (
          <button
            key={slide}
            type="button"
            className="auth-dot"
            aria-current={i === index}
            aria-label={t("goToSlide", { index: i + 1, title: t(`slide${slide}Title`) })}
            onClick={() => setIndex(i)}
          />
        ))}
      </div>
    </div>
  );
}
