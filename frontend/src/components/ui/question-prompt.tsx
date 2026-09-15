"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { CornerDownLeft, Pencil, X } from "lucide-react";
import { useLocale } from "next-intl";
import { cn } from "@/lib/utils";
import { Button } from "./button";

export interface QuestionPromptItem {
  question: string;
  reason?: string;
  details?: string;
  required?: boolean;
  options?: string[];
  /** Allow a free-form answer via the "Something else" field (default true). */
  allowCustom?: boolean;
}

export interface QuestionPromptAnswer {
  answer: string;
  skipped: boolean;
}

export interface QuestionPromptProps {
  /** Questions to ask, in order. The card steps through them one at a time. */
  questions: QuestionPromptItem[];
  /** Disable all controls (e.g. while the socket is offline). */
  disabled?: boolean;
  /** Called once every question has been answered or skipped. */
  onComplete: (answers: QuestionPromptAnswer[]) => void;
  onCancel?: () => void;
}

/**
 * Reusable question card. Steps through `questions` one at a time, collecting an
 * answer (a chosen option, free text, or a skip) for each, then returns them all
 * via `onComplete`. Native buttons support Tab/Enter; arrow keys navigate options.
 */
export function QuestionPrompt({
  questions,
  disabled = false,
  onComplete,
  onCancel,
}: QuestionPromptProps) {
  const zh = useLocale() === "zh";
  const [step, setStep] = useState(0);
  const answersRef = useRef<QuestionPromptAnswer[]>([]);
  const draftsRef = useRef<Record<number, string>>({});

  if (questions.length === 0) return null;
  const total = questions.length;
  const current = questions[step]!;

  const commit = (a: QuestionPromptAnswer) => {
    if (disabled || (current.required && a.skipped)) return;
    const next = [...answersRef.current];
    next[step] = a;
    answersRef.current = next;
    if (step + 1 >= total) onComplete(next.slice(0, total));
    else setStep((s) => s + 1);
  };

  const dismiss = () => {
    if (disabled || questions.slice(step).some((q) => q.required)) return;
    const remaining = questions.slice(step).map(() => ({ answer: "", skipped: true }));
    onComplete([...answersRef.current.slice(0, step), ...remaining]);
  };

  return (
    <div className="bg-muted/40 border-foreground/10 max-h-[55dvh] overflow-y-auto overscroll-contain rounded-2xl border">
      <div className="flex items-center justify-between gap-3 px-4 pt-2.5 pb-0.5">
        {total > 1 ? (
          <span className="text-muted-foreground font-mono text-[10px] tracking-wider uppercase">
            {zh ? `问题 ${step + 1} / ${total}` : `Question ${step + 1} of ${total}`}
          </span>
        ) : (
          <span />
        )}
        {onCancel ? (
          <button
            type="button"
            disabled={disabled}
            onClick={onCancel}
            className="text-muted-foreground min-h-9 text-xs"
          >
            {zh ? "取消本轮" : "Cancel turn"}
          </button>
        ) : (
          !questions.slice(step).some((q) => q.required) && (
            <button
              type="button"
              onClick={dismiss}
              disabled={disabled}
              aria-label={zh ? "跳过可选问题" : "Dismiss questions"}
              className="text-muted-foreground hover:text-foreground shrink-0 rounded-md p-1 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          )
        )}
      </div>

      {current.details && (
        <pre
          aria-label="本次调用参数"
          className="bg-background mx-4 my-3 max-h-48 overflow-auto rounded-lg p-3 text-xs break-all whitespace-pre-wrap"
        >
          {current.details}
        </pre>
      )}
      <SingleQuestion
        key={step}
        question={current.question}
        reason={current.reason}
        required={current.required}
        zh={zh}
        options={current.options ?? []}
        allowCustom={current.allowCustom ?? true}
        isLast={step + 1 >= total}
        disabled={disabled}
        initialText={draftsRef.current[step] ?? answersRef.current[step]?.answer ?? ""}
        onDraft={(text) => {
          draftsRef.current[step] = text;
        }}
        onAnswer={(text) => commit({ answer: text, skipped: false })}
        onSkip={() => commit({ answer: "", skipped: true })}
      />
      {step > 0 && (
        <button
          type="button"
          disabled={disabled}
          onClick={() => setStep((s) => s - 1)}
          className="text-muted-foreground mx-4 mb-2 min-h-9 text-xs"
        >
          {zh ? "返回上一题修改" : "Previous question"}
        </button>
      )}
    </div>
  );
}

interface SingleQuestionProps {
  question: string;
  reason?: string;
  details?: string;
  required?: boolean;
  zh: boolean;
  options: string[];
  allowCustom: boolean;
  isLast: boolean;
  disabled: boolean;
  initialText: string;
  onDraft: (text: string) => void;
  onAnswer: (answer: string) => void;
  onSkip: () => void;
}

function SingleQuestion({
  question,
  reason,
  required,
  zh,
  options,
  allowCustom,
  isLast,
  disabled,
  initialText,
  onDraft,
  onAnswer,
  onSkip,
}: SingleQuestionProps) {
  const hasOptions = options.length > 0;
  const [focusIdx, setFocusIdx] = useState(Math.max(0, options.indexOf(initialText)));
  // Open the free-form field straight away when there are no options to pick.
  const [customOpen, setCustomOpen] = useState(
    allowCustom && (!hasOptions || (!!initialText && !options.includes(initialText))),
  );
  const [customText, setCustomText] = useState(initialText);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (customOpen) inputRef.current?.focus();
    else containerRef.current?.querySelector<HTMLButtonElement>("li button")?.focus();
  }, [customOpen]);

  const submitCustom = () => {
    const text = customText.trim();
    if (text) onAnswer(text);
  };

  const onOptionKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (disabled || !["ArrowDown", "ArrowUp"].includes(e.key)) return;
    e.preventDefault();
    const next = Math.max(
      0,
      Math.min(options.length - 1, index + (e.key === "ArrowDown" ? 1 : -1)),
    );
    containerRef.current?.querySelectorAll<HTMLButtonElement>("li button")[next]?.focus();
  };

  return (
    <div
      ref={containerRef}
      tabIndex={-1}
      role="group"
      aria-label={zh ? "需要补充的信息" : "Question from the assistant"}
      className="outline-none"
    >
      <p className="text-foreground px-4 pb-2.5 text-[15px] leading-snug font-medium">{question}</p>

      {reason && (
        <p className="text-muted-foreground px-4 pb-2 text-xs leading-relaxed">{reason}</p>
      )}
      {required && (
        <p className="text-muted-foreground px-4 pb-2 text-xs">
          {zh ? "补充后继续 · 此问题不可跳过" : "Required before continuing"}
        </p>
      )}
      {hasOptions && (
        <ul className="divide-foreground/8 border-foreground/8 divide-y border-t">
          {options.map((option, i) => {
            const focused = i === focusIdx && !customOpen;
            return (
              <li key={`${option}-${i}`}>
                <button
                  type="button"
                  disabled={disabled}
                  onMouseEnter={() => setFocusIdx(i)}
                  onFocus={() => setFocusIdx(i)}
                  onKeyDown={(e) => onOptionKeyDown(e, i)}
                  onClick={() => onAnswer(option)}
                  className={cn(
                    "flex w-full items-center gap-3 px-4 py-3 text-left transition-colors",
                    focused ? "bg-foreground/[0.06]" : "hover:bg-foreground/[0.03]",
                  )}
                >
                  <span
                    className={cn(
                      "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg font-mono text-xs tabular-nums",
                      focused
                        ? "bg-foreground/10 text-foreground"
                        : "bg-foreground/5 text-muted-foreground",
                    )}
                  >
                    {i + 1}
                  </span>
                  <span className="text-foreground min-w-0 flex-1 text-sm break-words whitespace-normal">
                    {option}
                  </span>
                  {focused && <CornerDownLeft className="text-muted-foreground h-4 w-4 shrink-0" />}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <div className={cn("border-foreground/8", hasOptions && "border-t")}>
        {customOpen ? (
          <div className="flex items-center gap-2 px-4 py-2.5">
            <Pencil className="text-muted-foreground h-3.5 w-3.5 shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={customText}
              disabled={disabled}
              placeholder={zh ? "填写具体信息…" : "Type your answer…"}
              maxLength={2000}
              aria-label={zh ? "补充信息" : "Your answer"}
              onChange={(e) => {
                setCustomText(e.target.value);
                onDraft(e.target.value);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.nativeEvent.isComposing && !disabled) {
                  e.preventDefault();
                  submitCustom();
                }
              }}
              className="text-foreground placeholder:text-muted-foreground min-w-0 flex-1 bg-transparent text-sm outline-none"
            />
            <Button
              type="button"
              size="sm"
              className="h-7 text-xs"
              disabled={disabled || !customText.trim()}
              onClick={submitCustom}
            >
              {zh ? (isLast ? "提交并继续" : "下一题") : isLast ? "Done" : "Next"}
            </Button>
            {!required && (
              <Button type="button" variant="ghost" size="sm" disabled={disabled} onClick={onSkip}>
                {zh ? "采用默认值" : "Skip"}
              </Button>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-between gap-2 px-4 py-2.5">
            {allowCustom ? (
              <button
                type="button"
                disabled={disabled}
                onClick={() => setCustomOpen(true)}
                className="text-muted-foreground hover:text-foreground flex items-center gap-2 text-sm transition-colors"
              >
                <Pencil className="h-3.5 w-3.5" />
                {zh ? "自行填写" : "Something else"}
              </button>
            ) : (
              <span />
            )}
            {!required && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 text-xs"
                disabled={disabled}
                onClick={onSkip}
              >
                {zh ? "采用默认值" : "Skip"}
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
