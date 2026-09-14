"use client";

import { useEffect, useId, useState } from "react";
import { useLocale } from "next-intl";
import { ChevronRight } from "lucide-react";
import { useProject } from "@/components/projects/project-provider";
import { useAuthStore } from "@/stores";
import type { EffectiveConfig } from "@/lib/model-capabilities";

type Passage = {
  message_id: string;
  state: "available" | "changed";
  role: string | null;
  content: string | null;
  partial: boolean;
};

export function ContextUsage(props: {
  usage?: EffectiveConfig["context"];
  conversationId?: string;
  answerId: string;
}) {
  const userId = useAuthStore((s) => s.user?.id);
  const workspace = useProject();
  const projectId = workspace?.project?.id;
  if (!props.usage?.references.length || !props.conversationId || !userId) return null;
  // A scope change discards both the disclosure and its fetched private data.
  return (
    <Disclosure
      key={`${userId}:${projectId}:${props.conversationId}:${props.answerId}`}
      {...props}
      conversationId={props.conversationId}
      projectId={projectId}
    />
  );
}

function Disclosure({
  usage,
  conversationId,
  answerId,
  projectId,
}: {
  usage?: EffectiveConfig["context"];
  conversationId: string;
  answerId: string;
  projectId?: string;
}) {
  const zh = useLocale() === "zh";
  const id = useId();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Passage[] | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    let active = true;
    setItems(null);
    setError(false);
    void fetch(`/api/chat/conversations/${conversationId}/messages/${answerId}/context`, {
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
      headers: projectId ? { "X-Project-ID": projectId } : {},
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("unavailable");
        const data = await response.json();
        if (active) setItems(data.items);
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [open, projectId, conversationId, answerId]);
  return (
    <div className="text-muted-foreground text-xs">
      <button
        type="button"
        className="hover:text-foreground flex min-h-8 items-center gap-1.5"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
      >
        <ChevronRight size={13} className={open ? "rotate-90" : ""} />
        {zh
          ? `已衔接 ${usage?.references.length} 段历史`
          : `Used ${usage?.references.length} earlier passages`}
      </button>
      {open && (
        <div
          id={id}
          className="border-border my-1 max-h-72 space-y-3 overflow-auto rounded-xl border p-3"
        >
          <p>
            {zh
              ? "仅用于衔接当前会话，不作为知识库证据。"
              : "Context from this conversation; not knowledge-base evidence."}
          </p>
          {error ? (
            <p role="status">
              {zh
                ? "历史暂时无法读取，请收起后重试。"
                : "Could not load history. Close and reopen to retry."}
            </p>
          ) : !items ? (
            <p role="status">{zh ? "正在读取历史…" : "Loading history…"}</p>
          ) : (
            items.map((item) => (
              <div key={item.message_id}>
                {item.state === "changed" ? (
                  <p>{zh ? "原消息已修改或删除。" : "Original message changed or deleted."}</p>
                ) : (
                  <>
                    <p className="mb-1 font-medium">
                      {item.role === "user"
                        ? zh
                          ? "你"
                          : "You"
                        : zh
                          ? "助手的历史回答"
                          : "Earlier assistant answer"}
                      {item.partial && (zh ? " · 节选" : " · Excerpt")}
                    </p>
                    <p className="break-words whitespace-pre-wrap">{item.content}</p>
                  </>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
