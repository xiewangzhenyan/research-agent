"use client";

import { useEffect, useRef, useState, type ElementType, type ReactNode } from "react";

type RevealState = "idle" | "hidden" | "shown";

interface RevealProps {
  children: ReactNode;
  className?: string;
  as?: ElementType;
  id?: string;
  "aria-label"?: string;
  "aria-labelledby"?: string;
}

/**
 * Scroll reveal driven by CSS (`[data-reveal]` rules in globals.css).
 * Server HTML stays visible ("idle"): content that is already on screen, bots,
 * no-JS and screenshots never see a hidden state. Only content that starts
 * below the fold is hidden after hydration and animated when it scrolls in.
 * Children opt in with `.reveal-item` and an optional `--i` stagger index.
 */
export function Reveal({ children, className, as: Tag = "div", ...rest }: RevealProps) {
  const ref = useRef<HTMLElement>(null);
  const [state, setState] = useState<RevealState>("idle");

  useEffect(() => {
    const el = ref.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (el.getBoundingClientRect().top < window.innerHeight * 0.92) return;

    setState("hidden");
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return;
        setState("shown");
        observer.disconnect();
      },
      { rootMargin: "0px 0px -12% 0px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <Tag ref={ref} data-reveal={state} className={className} {...rest}>
      {children}
    </Tag>
  );
}
