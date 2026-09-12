"use client";
import { useEffect, useRef, useState } from "react";
import { Database, FileText, Quote } from "lucide-react";
import { APP_BRAND } from "@/lib/constants";
import { ResearchMark } from "@/components/brand/research-mark";
export function CosmicOrbit({ chinese }: { chinese: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const [running, setRunning] = useState(false);
  useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let visible = true;
    const sync = () => setRunning(visible && !motion.matches && !document.hidden);
    const observer = new IntersectionObserver(([entry]) => {
      visible = !!entry?.isIntersecting;
      sync();
    });
    if (ref.current) observer.observe(ref.current);
    motion.addEventListener("change", sync);
    document.addEventListener("visibilitychange", sync);
    sync();
    return () => {
      observer.disconnect();
      motion.removeEventListener("change", sync);
      document.removeEventListener("visibilitychange", sync);
    };
  }, []);
  return (
    <div ref={ref} className={`cosmic-orbit ${running ? "orbit-running" : ""}`} aria-hidden="true">
      <div className="orbit-stars" />
      <div className="orbit-halo" />
      <div className="orbit-track orbit-track-one">
        <i />
      </div>
      <div className="orbit-track orbit-track-two">
        <i />
      </div>
      <div className="orbit-track orbit-track-three">
        <i />
      </div>
      <div className="orbit-core">
        <ResearchMark size={38} />
        <span>{APP_BRAND}</span>
      </div>
      <div className="orbit-label orbit-label-a">
        <FileText />
        <span>{chinese ? "你的每一份资料" : "Your documents"}</span>
        <i />
      </div>
      <div className="orbit-label orbit-label-b">
        <Database />
        <span>{chinese ? "连接新的知识" : "Connected knowledge"}</span>
        <i />
      </div>
      <div className="orbit-label orbit-label-c">
        <Quote />
        <span>{chinese ? "每个答案 · 都有出处" : "Answers with sources"}</span>
        <i />
      </div>
      <span className="orbit-coordinate">25° KNOWLEDGE · ∞ POSSIBILITIES</span>
    </div>
  );
}
