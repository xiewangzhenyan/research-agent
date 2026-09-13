"use client";
import { currentProject, projectFetch } from "@/lib/project-scope";
import { useEffect, useRef } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Database } from "lucide-react";
import { useAuthStore, useConversationStore } from "@/stores";
import { useKnowledgeStore } from "@/stores/knowledge-store";
import { knowledgeRequest, type KnowledgeBase, type KnowledgeDocument } from "@/lib/knowledge";

export function KnowledgeSelector() {
  const generation = useRef(0);
  const userId = useAuthStore((s) => s.user?.id);
  const conversationId = useConversationStore((s) => s.currentConversationId);
  const { ids, documentIds, strict, ready, busy, error } = useKnowledgeStore();
  const { data, isError } = useQuery({
    queryKey: ["knowledge-bases", userId],
    queryFn: () => knowledgeRequest<{ items: KnowledgeBase[] }>("bases"),
    enabled: !!userId,
    staleTime: 0,
  });
  const documents = useQuery({
    queryKey: ["knowledge-scope-documents", userId, ...ids],
    queryFn: async () =>
      (
        await Promise.all(
          ids.map(async (id) => {
            const docs = await knowledgeRequest<KnowledgeDocument[]>(`bases/${id}/documents`);
            return docs.map((doc) => ({ ...doc, baseId: id }));
          }),
        )
      ).flat(),
    enabled: !!userId && !!ids.length && ready,
    staleTime: 0,
    refetchInterval: 15000,
  });
  useEffect(() => {
    let active = true;
    generation.current += 1;
    useKnowledgeStore.setState({
      ready: false,
      busy: true,
      error: null,
      scopeId: conversationId,
      documentsReady: false,
    });
    if (!conversationId) {
      const params = new URLSearchParams(window.location.search);
      const draft = params.get("knowledge");
      const document = params.get("document");
      useKnowledgeStore.setState({
        ids: draft ? [draft] : [...(currentProject()?.knowledge_base_ids ?? [])],
        documentIds: document ? [document] : null,
        strict: true,
        ready: true,
        busy: false,
      });
      return () => {
        generation.current += 1;
      };
    }
    projectFetch(`/api/conversations/${conversationId}`, { cache: "no-store" })
      .then(async (r) => {
        if (!r.ok) throw new Error("知识范围加载失败，请刷新重试。");
        return r.json();
      })
      .then((config) => {
        if (active)
          useKnowledgeStore.setState({
            ids: config.active_knowledge_base_ids ?? [],
            documentIds: config.active_knowledge_document_ids ?? null,
            strict: config.knowledge_strict ?? true,
            ready: true,
            busy: false,
          });
      })
      .catch((e) => {
        if (active) useKnowledgeStore.setState({ error: e.message, busy: false });
      });
    return () => {
      active = false;
      generation.current += 1;
    };
  }, [conversationId, userId]);
  const missingBases = data ? ids.filter((id) => !data.items.some((b) => b.id === id)) : [];
  const unavailableDocuments = documents.data
    ? (documentIds ?? []).filter(
        (id) => !documents.data.some((d) => d.id === id && d.status === "ready"),
      )
    : [];
  const scopeError = isError
    ? "知识库加载失败，请刷新重试。"
    : missingBases.length
      ? "选定知识库已删除或不可用，请重新选择。"
      : documentIds !== null && documents.isError
        ? "选定资料加载失败，请刷新重试。"
        : unavailableDocuments.length
          ? "选定资料已删除或尚未处理完成，请重新选择。"
          : null;
  useEffect(() => {
    if (ready)
      useKnowledgeStore.setState({ error: scopeError, documentsReady: documents.isSuccess });
  }, [ready, scopeError, documents.isSuccess]);

  async function save(nextIds: string[], nextStrict: boolean, nextDocuments: string[] | null) {
    const requestGeneration = generation.current;
    useKnowledgeStore.setState({ busy: true, error: null });
    try {
      if (conversationId) {
        const response = await projectFetch(`/api/conversations/${conversationId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            active_knowledge_base_ids: nextIds,
            active_knowledge_document_ids: nextDocuments,
            knowledge_strict: nextStrict,
          }),
        });
        if (!response.ok) throw new Error("保存知识范围失败，请重试。");
      }
      if (
        generation.current !== requestGeneration ||
        useAuthStore.getState().user?.id !== userId ||
        useConversationStore.getState().currentConversationId !== conversationId
      )
        return;
      useKnowledgeStore.setState({
        ids: nextIds,
        documentIds: nextDocuments,
        strict: nextStrict,
        busy: false,
      });
    } catch (e) {
      if (
        generation.current === requestGeneration &&
        useAuthStore.getState().user?.id === userId &&
        useKnowledgeStore.getState().scopeId === conversationId
      )
        useKnowledgeStore.setState({
          busy: false,
          error: e instanceof Error ? e.message : "保存失败",
        });
    }
  }
  return (
    <details className="border-border border-b px-4 py-3 text-xs" open={!!error}>
      <summary className="text-muted-foreground cursor-pointer">
        <Database className="text-brand mr-2 inline h-4 w-4" />
        {busy
          ? "正在同步知识范围…"
          : ids.length
            ? `${documentIds !== null ? `仅使用 ${documentIds.length} 条资料` : `已连接 ${ids.length} 个知识库`} · ${strict ? "严格资料问答" : "辅助问答"}`
            : "连接知识库 · 让回答有据可查"}
      </summary>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {error && (
          <span role="alert" className="w-full text-amber-400">
            {error}
          </span>
        )}
        {data?.items.map((b) => (
          <label key={b.id} className="flex items-center gap-2 rounded-lg border px-3 py-2">
            <input
              type="checkbox"
              checked={ids.includes(b.id)}
              disabled={
                busy || !ready || documentIds !== null || (!ids.includes(b.id) && ids.length >= 5)
              }
              onChange={(e) =>
                save(
                  e.target.checked
                    ? [...ids.filter((id) => !missingBases.includes(id)), b.id]
                    : ids.filter((id) => id !== b.id && !missingBases.includes(id)),
                  strict,
                  null,
                )
              }
            />
            {b.name}
          </label>
        ))}
        {!!missingBases.length && (
          <button
            type="button"
            className="underline"
            disabled={busy}
            onClick={() =>
              save(
                ids.filter((id) => !missingBases.includes(id)),
                strict,
                null,
              )
            }
          >
            移除失效范围
          </button>
        )}
        <Link href="/knowledge" className="text-brand px-2 py-2 underline underline-offset-4">
          管理知识库
        </Link>
        {!!ids.length && (
          <div className="w-full space-y-2 rounded-lg border p-3">
            <p className="font-medium">资料范围</p>
            <p className="text-muted-foreground">
              {documentIds === null
                ? "当前检索库内全部资料。勾选资料后，仅使用选中的 1–5 条。"
                : "仅检索选中资料；更换知识库前请先恢复全库范围。"}
            </p>
            {documents.isPending && <p>正在加载资料…</p>}
            {documents.isError && <p>资料列表暂时无法读取。</p>}
            {documents.data?.length === 0 && <p>尚无资料，请先添加并完成处理。</p>}
            <div className="max-h-44 space-y-2 overflow-y-auto">
              {documents.data?.map((doc) => (
                <label key={doc.id} className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    aria-label={`仅检索：${doc.title || doc.filename}`}
                    checked={documentIds?.includes(doc.id) ?? false}
                    disabled={
                      busy ||
                      doc.status !== "ready" ||
                      (documentIds?.includes(doc.id)
                        ? documentIds.length === 1
                        : (documentIds?.length ?? 0) >= 5)
                    }
                    onChange={(e) =>
                      save(
                        ids,
                        strict,
                        e.target.checked
                          ? [...(documentIds ?? []), doc.id]
                          : documentIds!.filter((id) => id !== doc.id),
                      )
                    }
                  />
                  <span className="min-w-0 break-words">
                    {doc.title || doc.filename}
                    {doc.status !== "ready" && " · 尚不可检索"}
                  </span>
                </label>
              ))}
            </div>
            {documentIds !== null && (
              <button
                type="button"
                className="text-brand underline"
                disabled={busy}
                onClick={() => save(ids, strict, null)}
              >
                恢复全库范围
              </button>
            )}
          </div>
        )}
        {!!ids.length && (
          <label className="flex w-full items-center gap-2 py-2">
            <input
              type="checkbox"
              checked={strict}
              disabled={busy || !ready}
              onChange={(e) => save(ids, e.target.checked, documentIds)}
            />
            仅根据选定资料回答；依据不足时明确说明
          </label>
        )}
        <span className="text-muted-foreground">
          知识库归账号所有，可跨项目复用 · 范围随会话保存
        </span>
      </div>
    </details>
  );
}
