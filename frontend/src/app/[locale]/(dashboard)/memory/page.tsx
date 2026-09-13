"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useLocale } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Brain, Plus, Search, Pin, Pencil, Trash2, MessageSquare, RefreshCw } from "lucide-react";
import { Button, Input, Switch } from "@/components/ui";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { MemoryEditor } from "@/components/memory/memory-editor";
import { apiClient } from "@/lib/api-client";
import { kindLabel, memoryError, memoryKey, type MemoryItem, type MemoryList } from "@/lib/memory";
import { useProject } from "@/components/projects/project-provider";
import { useAuthStore } from "@/stores";

export default function MemoryPage() {
  const userId = useAuthStore((s) => s.user?.id);
  const workspace = useProject();
  return <MemoryWorkspace key={`${userId}:${workspace?.project?.id ?? "default"}`} />;
}

function MemoryWorkspace() {
  const zh = useLocale() === "zh";
  const t = (cn: string, en: string) => (zh ? cn : en);
  const router = useRouter();
  const params = useSearchParams();
  const used = new Map(
    (params.get("used") ?? "")
      .split(",")
      .filter(Boolean)
      .map((v) => {
        const [id, revision] = v.split(":");
        return [id!, Number(revision)] as const;
      }),
  );
  const workspace = useProject();
  const userId = useAuthStore((s) => s.user?.id);
  const list = useQuery({
    queryKey: memoryKey(),
    queryFn: () => apiClient.get<MemoryList>("/memory"),
    enabled: !!userId,
    staleTime: 0,
  });
  const [search, setSearch] = useState("");
  const [editor, setEditor] = useState<MemoryItem | "new" | null>(null);
  const [removing, setRemoving] = useState<MemoryItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState<{
    items: MemoryItem[];
    omitted: number;
    status: string;
  } | null>(null);
  const [testing, setTesting] = useState(false);
  const visible =
    list.data?.items.filter(
      (item) =>
        (!used.size || used.has(item.id)) &&
        `${item.title}\n${item.content}`.toLocaleLowerCase().includes(search.toLocaleLowerCase()),
    ) ?? [];
  async function toggle(enabled: boolean) {
    if (!list.data) return;
    setBusy(true);
    setError("");
    try {
      await apiClient.put("/memory/settings", { enabled, revision: list.data.revision });
      setPreview(null);
    } catch (e) {
      setError(memoryError(e, zh));
    } finally {
      await list.refetch();
      setBusy(false);
    }
  }
  async function remove() {
    if (!removing) return;
    setBusy(true);
    setError("");
    try {
      await apiClient.delete(`/memory/${removing.id}`, {
        params: { revision: String(removing.revision) },
      });
      setRemoving(null);
      setPreview(null);
    } catch (e) {
      setError(memoryError(e, zh));
      setRemoving(null);
    } finally {
      await list.refetch();
      setBusy(false);
    }
  }
  async function source(item: MemoryItem) {
    setError("");
    try {
      const data = await apiClient.get<{ conversation_id: string }>(`/memory/${item.id}/source`);
      router.push(`/chat?id=${data.conversation_id}`);
    } catch (e) {
      setError(memoryError(e, zh));
    }
  }
  async function testRecall(event: React.FormEvent) {
    event.preventDefault();
    setTesting(true);
    setError("");
    try {
      setPreview(await apiClient.post("/memory/preview", { query }));
    } catch (e) {
      setError(memoryError(e, zh));
    } finally {
      setTesting(false);
    }
  }
  return (
    <div className="mx-auto w-full max-w-5xl shrink-0 space-y-6 pb-24 lg:pb-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-brand mb-2 text-xs">
            {workspace?.project?.name ?? t("默认项目", "Default project")}
          </p>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Brain className="text-brand h-6 w-6" />
            {t("项目记忆", "Project memory")}
          </h1>
          <p className="text-muted-foreground mt-2 max-w-xl text-sm leading-relaxed">
            {t(
              "让重要结论、约束和偏好在新聊天中延续。你确认保存，助手按需回忆。",
              "Carry decisions, constraints and preferences into new chats. You confirm what is saved; the assistant recalls relevant notes.",
            )}
          </p>
        </div>
        <Button onClick={() => setEditor("new")} disabled={!list.data}>
          <Plus className="mr-2 h-4 w-4" />
          {t("添加记忆", "Add memory")}
        </Button>
      </header>
      <section className="bg-card flex items-start justify-between gap-5 rounded-2xl border p-5">
        <div>
          <label htmlFor="memory-enabled" className="font-medium">
            {t("开启聊天记忆", "Enable chat memory")}
          </label>
          <p className="text-muted-foreground mt-2 max-w-2xl text-sm leading-relaxed">
            {t(
              "仅使用当前项目中你确认的记忆，其他项目和账号不会混入。关闭后不再读取记忆，当前会话历史仍保留。",
              "Only confirmed notes in this project are recalled. Other accounts and projects are excluded. Turning this off keeps existing chat history.",
            )}
          </p>
          <p className="text-muted-foreground mt-2 text-xs">
            {t(
              "严格知识库问答与后台任务暂不调用项目记忆。知识库仍属于账号，可跨项目复用。",
              "Strict knowledge answers and background tasks do not use project memory. Knowledge bases remain reusable account resources.",
            )}
          </p>
        </div>
        <Switch
          id="memory-enabled"
          checked={list.data?.enabled ?? false}
          disabled={!list.data || busy || list.isError}
          onCheckedChange={toggle}
        />
      </section>
      {error && (
        <p role="alert" className="text-destructive rounded-xl border p-4 text-sm">
          {error}
        </p>
      )}
      {list.isError ? (
        <div role="alert" className="rounded-xl border p-6">
          <p>{t("记忆暂时无法加载，请重试。", "Could not load memory. Please retry.")}</p>
          <Button className="mt-3" variant="outline" onClick={() => list.refetch()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            {t("重试", "Retry")}
          </Button>
        </div>
      ) : list.isPending ? (
        <p aria-live="polite">{t("正在加载项目记忆…", "Loading project memory…")}</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-muted-foreground text-sm">
              {list.data.items.length}/{list.data.limit} {t("条已保存", "saved")}
            </p>
            <div className="relative w-full sm:w-72">
              <Search className="text-muted-foreground absolute top-3 left-3 h-4 w-4" />
              <Input
                aria-label={t("搜索记忆", "Search memories")}
                placeholder={t("搜索标题或内容", "Search titles or content")}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>
          </div>
          {!!used.size && (
            <div className="text-muted-foreground rounded-xl border p-4 text-sm">
              {t(
                "正在查看此回答调用的记忆。内容可能已更新或删除；历史回答不会随之改写。",
                "Memories used by this answer may have since changed or been deleted. Historical answers stay unchanged.",
              )}{" "}
              <Link className="text-brand underline" href="/memory">
                {t("查看全部", "View all")}
              </Link>
            </div>
          )}
          {!visible.length ? (
            <div className="bg-muted/20 rounded-2xl border border-dashed px-6 py-12 text-center">
              <Brain className="text-muted-foreground mx-auto mb-4 h-8 w-8" />
              <p className="font-medium">
                {list.data.items.length || used.size
                  ? t("没有符合条件的记忆", "No matching memories")
                  : t("从一条值得保留的信息开始", "Start with something worth remembering")}
              </p>
              <p className="text-muted-foreground mx-auto mt-2 max-w-md text-sm">
                {t(
                  "例如“回答优先使用中文，保留专业术语英文”。也可以在聊天消息下点击记忆图标，整理后保存。",
                  "For example, save a preferred response language. You can also use the memory icon below a chat message and review it before saving.",
                )}
              </p>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {visible.map((item) => (
                <article
                  key={item.id}
                  className="bg-card flex min-w-0 flex-col rounded-2xl border p-5"
                >
                  <div className="mb-3 flex items-center gap-2">
                    <span className="text-muted-foreground rounded-md border px-2 py-1 text-xs">
                      {kindLabel(item.kind, zh)}
                    </span>
                    {item.pinned && (
                      <span className="text-brand flex items-center gap-1 text-xs">
                        <Pin size={12} />
                        {t("优先回忆", "Priority")}
                      </span>
                    )}
                    {used.has(item.id) && used.get(item.id) !== item.revision && (
                      <span className="text-xs text-amber-500">
                        {t("内容已更新", "Updated since use")}
                      </span>
                    )}
                  </div>
                  <h2 className="font-medium break-words">{item.title}</h2>
                  <p className="text-muted-foreground mt-2 flex-1 text-sm leading-relaxed break-words whitespace-pre-wrap">
                    {item.content}
                  </p>
                  <div className="mt-4 flex flex-wrap items-center gap-2 border-t pt-3">
                    {item.source_message_id && (
                      <Button size="sm" variant="ghost" onClick={() => source(item)}>
                        <MessageSquare className="mr-1 h-3.5 w-3.5" />
                        {t("来源会话", "Source chat")}
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => setEditor(item)}>
                      <Pencil className="mr-1 h-3.5 w-3.5" />
                      {t("编辑", "Edit")}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-muted-foreground hover:text-destructive ml-auto"
                      onClick={() => setRemoving(item)}
                      aria-label={`${t("删除", "Delete")} ${item.title}`}
                    >
                      <Trash2 size={15} />
                    </Button>
                  </div>
                </article>
              ))}
            </div>
          )}
          <details className="rounded-2xl border p-5">
            <summary className="cursor-pointer text-sm font-medium">
              {t("测试会回忆什么", "Test memory recall")}
            </summary>
            <p className="text-muted-foreground mt-3 text-xs leading-relaxed">
              {t(
                "按关键词匹配，优先包含置顶条目，并限制载入数量和长度。测试不会生成回答，也不会修改记忆。",
                "Keyword matching prioritizes pinned notes within a size limit. This test does not generate an answer or change notes.",
              )}
            </p>
            <form onSubmit={testRecall} className="mt-4 flex flex-col gap-3 sm:flex-row">
              <Input
                value={query}
                maxLength={2000}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setPreview(null);
                }}
                aria-label={t("测试问题", "Test question")}
                placeholder={t("输入你准备询问的问题", "Enter a question")}
              />
              <Button disabled={testing || !query.trim() || !list.data.enabled}>
                {testing ? t("测试中…", "Testing…") : t("测试回忆", "Test recall")}
              </Button>
            </form>
            {!list.data.enabled && (
              <p className="text-muted-foreground mt-3 text-xs">
                {t("开启聊天记忆后可测试召回。", "Enable memory to test recall.")}
              </p>
            )}
            {preview && (
              <div className="mt-4 space-y-2 text-sm" aria-live="polite">
                <p>
                  {preview.status === "disabled"
                    ? t(
                        "聊天记忆已关闭，请刷新设置。",
                        "Memory was disabled. Refresh the settings.",
                      )
                    : preview.items.length
                      ? t(
                          `本次将使用 ${preview.items.length} 条记忆`,
                          `${preview.items.length} memories would be used`,
                        )
                      : t(
                          "没有匹配的记忆。可以调整问题或将通用偏好设为优先回忆。",
                          "No matches. Rephrase the question or prioritize a general preference.",
                        )}
                </p>
                {preview.items.map((item) => (
                  <p key={item.id} className="bg-muted rounded-lg p-3">
                    {item.title}
                  </p>
                ))}
                {!!preview.omitted && (
                  <p className="text-muted-foreground text-xs">
                    {t(
                      `${preview.omitted} 条相关记忆因长度或数量限制未载入。可精简内容或调整优先级。`,
                      `${preview.omitted} matching notes exceeded the size limit. Shorten notes or adjust priority.`,
                    )}
                  </p>
                )}
              </div>
            )}
          </details>
        </>
      )}
      {editor && (
        <MemoryEditor
          item={editor === "new" ? undefined : editor}
          onClose={() => {
            setEditor(null);
            setPreview(null);
          }}
        />
      )}
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(open) => !open && !busy && setRemoving(null)}
        title={t("删除这条记忆？", "Delete this memory?")}
        description={t(
          "删除后，后续新回答不会再从项目记忆中调用它。已有会话记录不会被删除。",
          "Future answers will stop recalling this note. Existing conversations are kept.",
        )}
        confirmLabel={t("删除", "Delete")}
        cancelLabel={t("取消", "Cancel")}
        onConfirm={remove}
        loading={busy}
        destructive
      />
    </div>
  );
}
