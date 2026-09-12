"use client";

import { BookOpen, Code2, FileSearch, Sparkles } from "lucide-react";
import { useLocale } from "next-intl";

import { useAuth } from "@/hooks";

const PROMPTS_EN = [
  {
    icon: FileSearch,
    title: "Summarize my docs",
    prompt: "Summarize the key points from my latest indexed documents.",
  },
  {
    icon: BookOpen,
    title: "Explain a concept",
    prompt: "Explain how vector search and RAG work together — keep it under 200 words.",
  },
  {
    icon: Code2,
    title: "Write some code",
    prompt: "Write a Python function that hashes a password with bcrypt and verifies it.",
  },
  {
    icon: Sparkles,
    title: "Brainstorm",
    prompt: "Give me 5 ideas for an onboarding email sequence for a developer tool.",
  },
];

const PROMPTS_ZH = [
  { icon: FileSearch, title: "总结文档", prompt: "请总结我最近上传文档中的重点内容。" },
  { icon: BookOpen, title: "解释概念", prompt: "请用通俗语言解释向量搜索与 RAG 如何协同工作。" },
  { icon: Code2, title: "编写代码", prompt: "请编写一个清晰、安全并附带说明的 Python 示例。" },
  { icon: Sparkles, title: "头脑风暴", prompt: "请围绕我的目标给出 5 个可执行的创意。" },
];

interface ChatEmptyStateProps {
  onPick: (prompt: string) => void;
}

export function ChatEmptyState({ onPick }: ChatEmptyStateProps) {
  const { user } = useAuth();
  const isZh = useLocale() === "zh";
  const prompts = isZh ? PROMPTS_ZH : PROMPTS_EN;
  const firstName = user?.full_name?.split(" ")[0] || user?.email?.split("@")[0];

  return (
    <div className="chat-welcome mx-auto w-full max-w-2xl px-4 py-6 md:py-10">
      <div className="text-center">
        <div className="bg-brand/10 text-brand mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-2xl">
          <Sparkles className="h-5 w-5" />
        </div>
        <h2 className="text-foreground font-display text-2xl font-semibold tracking-tight md:text-3xl">
          {isZh
            ? firstName
              ? `${firstName}，今天想从哪里开始？`
              : "今天想从哪里开始？"
            : firstName
              ? `How can I help, ${firstName}?`
              : "How can I help today?"}
        </h2>
        <p className="text-muted-foreground mx-auto mt-2 max-w-md text-sm leading-relaxed">
          {isZh
            ? "连接知识库，让回答有据可查。"
            : "Connect your knowledge base for answers with source citations."}
        </p>
      </div>

      <div className="chat-prompt-shortcuts mt-6 flex flex-wrap justify-center gap-2">
        {prompts.map((p) => (
          <button
            key={p.title}
            type="button"
            onClick={() => onPick(p.prompt)}
            className="group border-border bg-card hover:border-brand/40 hover:bg-accent flex min-h-10 items-center gap-2 rounded-lg border px-3 py-2 text-left transition-colors"
          >
            <span className="text-muted-foreground group-hover:text-brand flex shrink-0 items-center justify-center transition-colors">
              <p.icon className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-foreground text-sm font-medium">{p.title}</p>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
