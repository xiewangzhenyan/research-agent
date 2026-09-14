"use client";

import Link from "next/link";
import { useState } from "react";
import { Check, ChevronDown, Sliders, ArrowUpRight } from "lucide-react";
import { useLocale } from "next-intl";
import { ChatSettingsPanel } from "./chat-settings-panel";
import { cn } from "@/lib/utils";
import { ReasoningControl } from "./reasoning-control";
import type { GenerationOptions } from "@/lib/model-capabilities";
import { useGenerationConfig } from "@/hooks/use-generation-config";

type Effort = "low" | "medium" | "high" | null;
interface ChatControlsProps {
  value?: GenerationOptions;
  onChange?: (value: GenerationOptions) => void;
  disabled?: boolean;
  onModelChange?: (model: string | null) => void;
  onTemperatureChange?: (value: number | null) => void;
  onThinkingEffortChange?: (value: Effort) => void;
}

export function ChatControls({
  value,
  onChange,
  disabled = false,
  onModelChange,
  onTemperatureChange,
  onThinkingEffortChange,
}: ChatControlsProps) {
  const zh = useLocale() === "zh";
  const query = useGenerationConfig();
  const { data } = query;
  const [local, setLocal] = useState<GenerationOptions>({});
  const options = value ?? local;
  const model = options.model ?? null;
  const temperature = options.temperature ?? null;
  const topP = options.top_p ?? null;
  const outputLimit = options.max_output_tokens ?? null;
  const effort = options.thinking_effort === "off" ? null : (options.thinking_effort ?? null);
  const [tab, setTab] = useState<"model" | "settings">("model");
  const current = data?.models.find((item) => item.id === (model ?? data.default));
  const customized = Object.entries(options).some(([key, v]) => key !== "model" && v != null);
  const change = (next: GenerationOptions) => {
    setLocal(next);
    onChange?.(next);
    onModelChange?.(next.model ?? null);
    onTemperatureChange?.(next.temperature ?? null);
    onThinkingEffortChange?.(
      next.thinking_effort === "off" ? null : (next.thinking_effort ?? null),
    );
  };
  const pick = (model: string | null) => change({ model });
  const reset = () => change({ model });
  const invalid =
    data &&
    (!current ||
      (temperature !== null && !current.temperature) ||
      (topP !== null && !current.top_p) ||
      (effort !== null && !current.thinking_efforts.includes(effort)) ||
      (outputLimit !== null &&
        (outputLimit < (current.output_token_limits?.[0] ?? 256) ||
          outputLimit > (current.output_token_limits?.[1] ?? 8000))));
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
    <ChatSettingsPanel
      trigger={
        <button
          type="button"
          disabled={disabled}
          aria-label={zh ? "聊天模型与设置" : "Chat controls"}
          data-chat-settings-trigger
          className="text-muted-foreground hover:text-foreground hover:bg-muted inline-flex min-h-9 max-w-full items-center gap-1.5 rounded-full px-2 text-xs"
        >
          <Sliders className="h-3.5 w-3.5" />
          <span className="max-w-[125px] truncate sm:max-w-[220px]">
            {model ??
              (data
                ? `${zh ? "默认" : "Default"} · ${data.default}`
                : zh
                  ? "模型与设置"
                  : "Model settings")}
          </span>
          {customized && (
            <span
              className="bg-brand h-1.5 w-1.5 rounded-full"
              aria-label={zh ? "已自定义" : "Customized"}
            />
          )}
          <ChevronDown className="h-3 w-3" />
        </button>
      }
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
        {query.isError ? (
          <div role="alert" className="space-y-2 text-sm">
            <p>
              {data
                ? zh
                  ? "更新失败，暂用上次获取的模型配置。"
                  : "Update failed. Showing the last configuration."
                : zh
                  ? "配置加载失败，暂时无法调整参数。"
                  : "Configuration unavailable. Controls are disabled."}
            </p>
            <button
              type="button"
              onClick={() => query.refetch()}
              disabled={query.isFetching}
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
        {invalid && (
          <p role="alert" className="text-destructive text-xs">
            {zh
              ? "已保存的参数不符合当前模型策略，请重新选择模型或恢复默认。"
              : "Saved settings no longer match model policy. Select a model or reset."}
            <button type="button" onClick={() => change({})} className="ml-2 underline">
              {zh ? "恢复全部默认" : "Reset all"}
            </button>
          </p>
        )}
        {data && tab === "model" && (
          <>
            <p className="text-muted-foreground text-xs leading-relaxed">
              {zh
                ? "选择本会话后续消息使用的模型。切换后，回答参数恢复为该模型的默认值。"
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
        {data && tab === "settings" && (
          <>
            <div className="space-y-2">
              <label htmlFor="chat-temp" className="text-sm font-medium">
                {zh ? "回答随机性（温度）" : "Temperature"}
              </label>
              <p className="text-muted-foreground text-xs">
                {current?.temperature
                  ? topP !== null
                    ? zh
                      ? "未发送温度参数（已调整 Top P）"
                      : "Temperature omitted while Top P is set"
                    : `${zh ? "当前值" : "Current"}：${temperature ?? current.defaults.temperature}`
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
                disabled={!current?.temperature || (!onChange && !onTemperatureChange)}
                onChange={(event) => {
                  const value = Number(event.target.value);
                  change({ ...options, temperature: value, top_p: null });
                }}
                className="accent-foreground min-h-8 w-full disabled:cursor-not-allowed disabled:opacity-30"
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
              <ReasoningControl
                value={effort}
                supported={current?.thinking_efforts ?? []}
                disabled={!onChange && !onThinkingEffortChange}
                onChange={(value) => {
                  change({ ...options, thinking_effort: value });
                }}
              />
              <p className="text-muted-foreground text-xs leading-relaxed">
                {zh
                  ? "默认表示沿用服务器策略；未指定推理参数不代表关闭模型内部推理。"
                  : "Default follows server policy. Omitting this parameter does not disable internal reasoning."}
              </p>
            </div>
            <details className="border-border border-t pt-3">
              <summary className="min-h-9 cursor-pointer text-sm font-medium">
                {zh ? "更多参数" : "Advanced parameters"}
              </summary>
              <div className="space-y-4 pt-2">
                <div className="space-y-2">
                  <label htmlFor="chat-top-p" className="text-sm">
                    Top P · {topP ?? (zh ? "默认" : "Default")}
                  </label>
                  <input
                    id="chat-top-p"
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    value={topP ?? 1}
                    disabled={!current?.top_p || !onChange}
                    onChange={(e) =>
                      change({ ...options, top_p: Number(e.target.value), temperature: null })
                    }
                    className="accent-foreground min-h-8 w-full disabled:opacity-30"
                  />
                  <p className="text-muted-foreground text-xs">
                    {current?.top_p
                      ? zh
                        ? "调整 Top P 时不发送温度参数；两者择一调整。"
                        : "Adjust either Top P or temperature. Changing one resets the other."
                      : zh
                        ? "当前模型未开放 Top P。"
                        : "Top P is not enabled for this model."}
                  </p>
                </div>
                <div className="space-y-2">
                  <label htmlFor="chat-output-limit" className="text-sm">
                    {zh ? "输出长度上限（Token）" : "Output token limit"}
                  </label>
                  <select
                    id="chat-output-limit"
                    value={outputLimit ?? ""}
                    disabled={!current || !onChange}
                    onChange={(e) =>
                      change({
                        ...options,
                        max_output_tokens: e.target.value ? Number(e.target.value) : null,
                      })
                    }
                    className="border-border bg-background min-h-10 w-full rounded-lg border px-3 text-sm"
                  >
                    <option value="">
                      {zh ? "服务器默认" : "Server default"} ·{" "}
                      {current?.defaults.max_output_tokens ?? 8000}
                    </option>
                    {Array.from(
                      new Set([
                        512,
                        1024,
                        2048,
                        4096,
                        8000,
                        16000,
                        32000,
                        ...(outputLimit ? [outputLimit] : []),
                      ]),
                    )
                      .sort((a, b) => a - b)
                      .filter(
                        (n) =>
                          n === outputLimit ||
                          (n >= (current?.output_token_limits?.[0] ?? 256) &&
                            n <= (current?.output_token_limits?.[1] ?? 8000)),
                      )
                      .map((n) => (
                        <option key={n} value={n}>
                          {n.toLocaleString()}
                        </option>
                      ))}
                  </select>
                  <p className="text-muted-foreground text-xs leading-relaxed">
                    {zh
                      ? "这是每次模型输出的上限，包含推理 Token；上限过低可能导致长回答或文件内容不完整。"
                      : "Includes reasoning tokens per model response. A low limit may cut off long answers or documents."}
                  </p>
                </div>
              </div>
            </details>
            {customized && (
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
                ? "参数随下一条消息保存到本会话，重新打开后恢复。实际参数随回答保存。"
                : "Settings are saved with your next message and restored when you reopen this conversation."}
            </p>
          </>
        )}
      </div>
      <div className="border-border border-t px-4 py-3">
        <Link
          href="/models"
          className="text-brand flex min-h-8 items-center justify-between text-xs"
        >
          {zh ? "查看 Embedding、Rerank 与平台能力" : "View embedding, reranking and capabilities"}
          <ArrowUpRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </ChatSettingsPanel>
  );
}
