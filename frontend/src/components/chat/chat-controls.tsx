"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Check, ChevronDown, Sliders, ArrowUpRight } from "lucide-react";
import { useLocale } from "next-intl";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui";
import { cn } from "@/lib/utils";
import { fetchCapabilities, type AgentCapabilities } from "@/lib/model-capabilities";

type Effort = "low" | "medium" | "high" | null;
interface ChatControlsProps {
  onModelChange?: (model: string | null) => void;
  onTemperatureChange?: (value: number | null) => void;
  onThinkingEffortChange?: (value: Effort) => void;
}

export function ChatControls({
  onModelChange,
  onTemperatureChange,
  onThinkingEffortChange,
}: ChatControlsProps) {
  const zh = useLocale() === "zh";
  const [data, setData] = useState<AgentCapabilities | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [model, setModel] = useState<string | null>(null);
  const [temperature, setTemperature] = useState<number | null>(null);
  const [effort, setEffort] = useState<Effort>(null);
  const [tab, setTab] = useState<"model" | "settings">("model");
  useEffect(() => {
    const controller = new AbortController();
    setError(false);
    fetchCapabilities(controller.signal)
      .then(setData)
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      });
    return () => controller.abort();
  }, [attempt]);
  const current = data?.models.find((item) => item.id === (model ?? data.default));
  const pick = (value: string | null) => {
    setModel(value);
    setTemperature(null);
    setEffort(null);
    onModelChange?.(value);
    onTemperatureChange?.(null);
    onThinkingEffortChange?.(null);
  };
  const reset = () => {
    setTemperature(null);
    setEffort(null);
    onTemperatureChange?.(null);
    onThinkingEffortChange?.(null);
  };
  const effortLabel = (value: string | null | undefined) =>
    value === "low"
      ? zh
        ? "低"
        : "Low"
      : value === "medium"
        ? zh
          ? "中"
          : "Medium"
        : value === "high"
          ? zh
            ? "高"
            : "High"
          : zh
            ? "由模型服务决定"
            : "Provider default";

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={zh ? "聊天模型与设置" : "Chat controls"}
          className="border-border bg-card text-muted-foreground hover:text-foreground inline-flex min-h-9 items-center gap-1.5 rounded-full border px-3 text-xs"
        >
          <Sliders className="h-3.5 w-3.5" />
          <span className="max-w-[180px] truncate">
            {model ??
              (data
                ? `${zh ? "默认" : "Default"} · ${data.default}`
                : zh
                  ? "模型与设置"
                  : "Model settings")}
          </span>
          {(temperature !== null || effort !== null) && (
            <span
              className="bg-brand h-1.5 w-1.5 rounded-full"
              aria-label={zh ? "已自定义" : "Customized"}
            />
          )}
          <ChevronDown className="h-3 w-3" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={8}
        className="border-border bg-popover w-[min(380px,calc(100vw-24px))] overflow-hidden rounded-2xl p-0 shadow-lg"
      >
        <div className="border-border flex gap-2 border-b p-2">
          {(["model", "settings"] as const).map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={tab === item}
              onClick={() => setTab(item)}
              className={cn(
                "min-h-10 flex-1 rounded-xl text-sm",
                tab === item ? "bg-accent text-foreground font-medium" : "text-muted-foreground",
              )}
            >
              {item === "model" ? (zh ? "生成模型" : "Model") : zh ? "回答设置" : "Settings"}
            </button>
          ))}
        </div>
        <div className="max-h-[min(440px,60vh)] space-y-4 overflow-y-auto p-4">
          {error ? (
            <div role="alert" className="space-y-2 text-sm">
              <p>
                {zh
                  ? "配置加载失败，暂时无法调整参数。"
                  : "Configuration unavailable. Controls are disabled."}
              </p>
              <button
                type="button"
                onClick={() => setAttempt((n) => n + 1)}
                className="text-brand min-h-10 underline"
              >
                {zh ? "重新加载" : "Retry"}
              </button>
            </div>
          ) : !data ? (
            <p role="status" className="text-muted-foreground text-sm">
              {zh ? "正在读取服务器配置…" : "Loading configuration…"}
            </p>
          ) : null}
          {data && !error && tab === "model" && (
            <>
              <p className="text-muted-foreground text-xs leading-relaxed">
                {zh
                  ? "选择本页后续消息使用的模型。切换后，回答参数恢复为该模型的默认值。"
                  : "Choose the model for subsequent messages. Switching resets parameter overrides."}
              </p>
              <ul className="space-y-1.5">
                {[
                  {
                    value: null,
                    label: `${zh ? "服务器默认" : "Server default"} · ${data.default}`,
                  },
                  ...data.models.map((m) => ({ value: m.id, label: m.id })),
                ].map((item) => (
                  <li key={item.value ?? "default"}>
                    <button
                      type="button"
                      onClick={() => pick(item.value)}
                      aria-pressed={model === item.value}
                      className={cn(
                        "flex min-h-11 w-full items-center justify-between gap-2 rounded-xl border px-3 py-2 text-left text-sm",
                        model === item.value
                          ? "border-brand/40 bg-brand/10"
                          : "border-border hover:bg-accent",
                      )}
                    >
                      <span className="break-all">{item.label}</span>
                      {model === item.value && <Check className="text-brand h-4 w-4 shrink-0" />}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
          {data && !error && tab === "settings" && (
            <>
              <div className="space-y-2">
                <label htmlFor="chat-temp" className="text-sm font-medium">
                  {zh ? "回答随机性（温度）" : "Temperature"}
                </label>
                <p className="text-muted-foreground text-xs">
                  {current?.temperature
                    ? `${zh ? "当前值" : "Current"}：${temperature ?? current.defaults.temperature}`
                    : zh
                      ? "当前模型未开放温度设置，不会向模型发送该参数。"
                      : "Temperature is not enabled for this model and will not be sent."}
                </p>
                <input
                  id="chat-temp"
                  type="range"
                  min={0}
                  max={2}
                  step={0.05}
                  value={temperature ?? current?.defaults.temperature ?? 0.7}
                  disabled={!current?.temperature || !onTemperatureChange}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    setTemperature(value);
                    onTemperatureChange?.(value);
                  }}
                  className="accent-brand min-h-8 w-full disabled:cursor-not-allowed disabled:opacity-30"
                />
                <div className="text-muted-foreground flex justify-between text-xs">
                  <span>{zh ? "更稳定" : "More consistent"}</span>
                  <span>{zh ? "更多变化" : "More varied"}</span>
                </div>
              </div>
              <div className="space-y-2">
                <p className="text-sm font-medium">{zh ? "推理强度" : "Reasoning effort"}</p>
                <p className="text-muted-foreground text-xs">
                  {current?.thinking_efforts.length
                    ? `${zh ? "当前值" : "Current"}：${effortLabel(effort ?? current.defaults.thinking_effort)}`
                    : zh
                      ? "当前模型未开放推理强度设置。"
                      : "Reasoning controls are not enabled for this model."}
                </p>
                <div className="grid grid-cols-4 gap-1.5">
                  {([null, "low", "medium", "high"] as const).map((value) => (
                    <button
                      key={value ?? "default"}
                      type="button"
                      aria-pressed={effort === value}
                      disabled={
                        !current?.thinking_efforts.length ||
                        !onThinkingEffortChange ||
                        (value !== null && !current.thinking_efforts.includes(value))
                      }
                      onClick={() => {
                        setEffort(value);
                        onThinkingEffortChange?.(value);
                      }}
                      className={cn(
                        "min-h-10 rounded-lg border text-xs disabled:opacity-35",
                        effort === value ? "border-brand/40 bg-brand/10" : "border-border",
                      )}
                    >
                      {value === null ? (zh ? "默认" : "Default") : effortLabel(value)}
                    </button>
                  ))}
                </div>
                <p className="text-muted-foreground text-xs leading-relaxed">
                  {zh
                    ? "默认表示沿用服务器策略；未指定推理参数不代表关闭模型内部推理。"
                    : "Default follows server policy. Omitting this parameter does not disable internal reasoning."}
                </p>
              </div>
              {(temperature !== null || effort !== null) && (
                <button
                  type="button"
                  onClick={reset}
                  className="text-brand min-h-10 text-sm underline"
                >
                  {zh ? "恢复服务器默认" : "Reset to server defaults"}
                </button>
              )}
              <p className="text-muted-foreground text-xs leading-relaxed">
                {zh
                  ? "设置对普通对话和严格资料问答均生效，实际参数随回答保存。"
                  : "Settings apply to chat and grounded answers. Actual parameters are saved with each answer."}
              </p>
            </>
          )}
        </div>
        <div className="border-border border-t px-4 py-3">
          <Link
            href="/models"
            className="text-brand flex min-h-8 items-center justify-between text-xs"
          >
            {zh
              ? "查看 Embedding、Rerank 与平台能力"
              : "View embedding, reranking and capabilities"}
            <ArrowUpRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
}
