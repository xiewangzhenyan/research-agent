"use client";

import { useEffect, useState } from "react";
import { useLocale } from "next-intl";

type State = { ms: number | null; status: "pending" | "good" | "slow" | "down" };
const INTERVAL_MS = 30_000;
const SLOW_MS = 600;

/**
 * Round-trip time from this browser to the API (via /api/health), refreshed every
 * 30 s while the tab is visible. A real measurement, shown like an instrument readout.
 */
export function LinkMeter() {
  const zh = useLocale() === "zh";
  const [state, setState] = useState<State>({ ms: null, status: "pending" });

  useEffect(() => {
    let inFlight = false;
    const ping = async () => {
      if (document.hidden || inFlight) return;
      inFlight = true;
      const started = performance.now();
      try {
        const res = await fetch("/api/health", { cache: "no-store" });
        const ms = Math.round(performance.now() - started);
        setState({ ms, status: !res.ok ? "down" : ms < SLOW_MS ? "good" : "slow" });
      } catch {
        setState({ ms: null, status: "down" });
      } finally {
        inFlight = false;
      }
    };
    void ping();
    const timer = window.setInterval(ping, INTERVAL_MS);
    const onVisible = () => void ping();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  const value = state.status === "down" ? "ERR" : state.ms === null ? "···" : `${state.ms}ms`;
  const label = zh
    ? state.status === "down"
      ? "服务暂时无法连接"
      : `到服务器的往返延迟 ${state.ms ?? "—"} 毫秒`
    : state.status === "down"
      ? "Service unreachable"
      : `Round trip to the server: ${state.ms ?? "—"} ms`;

  return (
    <span className="link-meter" data-state={state.status} title={label} aria-label={label}>
      <i aria-hidden />
      <span aria-hidden>API {value}</span>
    </span>
  );
}
