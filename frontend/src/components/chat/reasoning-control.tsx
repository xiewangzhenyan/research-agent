"use client";

import { useId } from "react";
import { useLocale } from "next-intl";

type Effort = "low" | "medium" | "high" | null;
const LEVELS: Effort[] = [null, "low", "medium", "high"];

export function ReasoningControl({
  value,
  supported,
  disabled,
  onChange,
}: {
  value: Effort;
  supported: string[];
  disabled?: boolean;
  onChange: (effort: Effort) => void;
}) {
  const zh = useLocale() === "zh";
  const id = useId();
  const levels = LEVELS.filter((level) => level === null || supported.includes(level));
  const index = Math.max(0, levels.indexOf(value));
  const label = (level: Effort) =>
    level === null
      ? zh
        ? "默认"
        : "Default"
      : { low: zh ? "低" : "Low", medium: zh ? "中" : "Medium", high: zh ? "高" : "High" }[level];
  const unavailable = disabled || levels.length < 2;
  return (
    <div className={unavailable ? "opacity-45" : ""}>
      <div className="relative mx-3 flex h-9 items-center">
        <div className="bg-muted h-1 w-full rounded-full" />
        <div
          className="reasoning-thumb bg-foreground pointer-events-none absolute h-4 w-4 -translate-x-1/2 rounded-full shadow-sm"
          style={{ left: `${levels.length > 1 ? (index / (levels.length - 1)) * 100 : 0}%` }}
        />
        <input
          id={id}
          aria-label={zh ? "推理强度" : "Reasoning effort"}
          aria-valuetext={label(value)}
          type="range"
          min={0}
          max={Math.max(1, levels.length - 1)}
          step={1}
          value={index}
          disabled={unavailable}
          onChange={(event) => onChange(levels[Number(event.target.value)] ?? null)}
          className="absolute inset-0 w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
        />
      </div>
      <div className="flex justify-between gap-1">
        {LEVELS.map((level) => (
          <button
            key={level ?? "default"}
            type="button"
            disabled={
              disabled || !supported.length || (level !== null && !supported.includes(level))
            }
            aria-pressed={value === level}
            onClick={() => onChange(level)}
            className={`min-h-9 flex-1 rounded-lg text-xs disabled:opacity-35 ${value === level ? "bg-muted text-foreground font-medium" : "text-muted-foreground hover:text-foreground"}`}
          >
            {label(level)}
          </button>
        ))}
      </div>
    </div>
  );
}
