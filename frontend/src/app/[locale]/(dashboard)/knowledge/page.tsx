"use client";
import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Search,
  FolderOpen,
  Database,
  Upload,
  Plus,
  FileText,
  ArrowUpRight,
} from "lucide-react";
import { toast } from "sonner";
import { useAuthStore } from "@/stores";
import { DocumentActions } from "@/components/knowledge/document-actions";
import { EntryEditor } from "@/components/knowledge/entry-editor";
import { ParseReport } from "@/components/knowledge/parse-report";
import { RetrievalTester } from "@/components/knowledge/retrieval-tester";
import { ChunkPreview } from "@/components/knowledge/chunk-preview";
import { ChunkingSettings } from "@/components/knowledge/chunking-settings";
import {
  knowledgeRequest as api,
  type KnowledgeBase,
  type KnowledgeDocument,
  type KnowledgeHit,
} from "@/lib/knowledge";
import {
  Button,
  Input,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/components/ui";

const stages: Record<string, string> = {
  pending: "排队中",
  processing: "处理中",
  parsing: "解析文字",
  chunking: "智能分块",
  embedding: "生成向量",
  ready: "可检索",
  failed: "处理失败",
};
const active = new Set(["pending", "processing", "parsing", "chunking", "embedding"]);
export default function KnowledgePage() {
  const userId = useAuthStore((s) => s.user?.id);
  return userId ? <KnowledgeWorkspace key={userId} userId={userId} /> : null;
}
function KnowledgeWorkspace({ userId }: { userId: string }) {
  const cache = useQueryClient();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [baseQuery, setBaseQuery] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [fileQuery, setFileQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [kindFilter, setKindFilter] = useState("all");
  const [editor, setEditor] = useState<{
    baseId: string;
    kind: "manual" | "faq";
    documentId?: string;
  } | null>(null);
  const [chunkPage, setChunkPage] = useState(0);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [chunkError, setChunkError] = useState("");
  const chunkRequest = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      chunkRequest.current?.abort();
    },
    [],
  );
  const [uploads, setUploads] = useState<{
    base: string;
    items: { name: string; result: string; failed: boolean }[];
  } | null>(null);
  const [preview, setPreview] = useState<{
    base: string;
    filename: string;
    items: KnowledgeHit[];
  } | null>(null);
  const [removal, setRemoval] = useState<{ path: string; name: string } | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const bases = useQuery({
    queryKey: ["knowledge-bases", userId],
    queryFn: () => api<{ items: KnowledgeBase[] }>("bases"),
    enabled: !!userId,
  });
  const current = bases.data?.items.find((b) => b.id === searchParams.get("base"));
  const visibleBases = bases.data?.items.filter((b) =>
    `${b.name} ${b.description || ""}`.toLocaleLowerCase().includes(baseQuery.toLocaleLowerCase()),
  );
  const docs = useQuery({
    queryKey: ["knowledge-documents", userId, current?.id],
    queryFn: () => api<KnowledgeDocument[]>(`bases/${current!.id}/documents`),
    enabled: !!current,
    refetchInterval: (q) => (q.state.data?.some((d) => active.has(d.status)) ? 1500 : false),
  });
  const refresh = async () => {
    await cache.invalidateQueries({ queryKey: ["knowledge-bases", userId] });
    await cache.invalidateQueries({ queryKey: ["knowledge-documents", userId] });
  };
  const fail = (e: unknown) => toast.error(e instanceof Error ? e.message : "操作失败");
  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const b = await api<KnowledgeBase>("bases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description }),
      });
      chooseBase(b.id);
      await refresh();
      setCreateOpen(false);
      setName("");
      setDescription("");
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function upload(files: FileList | null) {
    if (!files || !current || busy) return;
    const target = current.id;
    const outcomes: { name: string; result: string; failed: boolean }[] = [];
    const known = new Set(docs.data?.map((d) => d.id));
    setBusy(true);
    setUploads({ base: target, items: [] });
    try {
      for (const file of Array.from(files)) {
        try {
          if (!file.size || file.size > 10 * 1024 * 1024)
            throw new Error("文件不能为空，且不能超过 10 MB");
          const form = new FormData();
          form.set("file", file);
          const doc = await api<KnowledgeDocument>(`bases/${target}/documents`, {
            method: "POST",
            body: form,
          });
          outcomes.push({
            name: file.name,
            result: known.has(doc.id) ? "文件已存在" : "已提交处理",
            failed: false,
          });
          known.add(doc.id);
        } catch (e) {
          outcomes.push({
            name: file.name,
            result: e instanceof Error ? e.message : "上传失败，请重试",
            failed: true,
          });
        }
        setUploads({ base: target, items: [...outcomes] });
      }
      await refresh();
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }
  async function showChunks(d: KnowledgeDocument) {
    chunkRequest.current?.abort();
    const controller = new AbortController();
    chunkRequest.current = controller;
    const base = current!.id;
    setChunkPage(0);
    setChunkError("");
    setChunksLoading(true);
    setPreview({ base, filename: d.title || d.filename, items: [] });
    try {
      const r = await api<{ items: KnowledgeHit[] }>(`documents/${d.id}/chunks`, {
        signal: controller.signal,
      });
      if (!controller.signal.aborted)
        setPreview({ base, filename: d.title || d.filename, items: r.items });
    } catch (e) {
      if (!controller.signal.aborted)
        setChunkError(e instanceof Error ? e.message : "加载失败，请关闭后重试");
    } finally {
      if (!controller.signal.aborted) setChunksLoading(false);
    }
  }
  const ready = docs.data?.filter((d) => d.status === "ready").length || 0;
  const processing = docs.data?.filter((d) => active.has(d.status)).length || 0;
  const failed = docs.data?.filter((d) => d.status === "failed").length || 0;
  const filteredDocs = docs.data?.filter(
    (d) =>
      (d.title || d.filename).toLocaleLowerCase().includes(fileQuery.toLocaleLowerCase()) &&
      (kindFilter === "all" || (d.source_kind || "file") === kindFilter) &&
      (statusFilter === "all" ||
        (statusFilter === "active" ? active.has(d.status) : d.status === statusFilter)),
  );
  const chooseBase = (value: string) => {
    router.push(`/knowledge?base=${encodeURIComponent(value)}`);
    setFileQuery("");
    setStatusFilter("all");
    setKindFilter("all");
    chunkRequest.current?.abort();
    setPreview(null);
  };

  return (
    <div className="knowledge-workspace mx-auto w-full max-w-7xl space-y-4 pb-8 sm:space-y-6">
      <header className="workspace-page-header">
        <div className="min-w-0">
          {current && (
            <Link href="/knowledge" className="workspace-back">
              <ArrowLeft size={15} />
              全部知识库
            </Link>
          )}
          <h1>{current ? current.name : "知识库"}</h1>
          <p>
            {current
              ? current.description || "管理资料、检查检索结果，让每一次回答有据可查。"
              : "账号下的全部知识库，可在不同项目中重复选用。"}
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)} className="mint-action">
          <Plus className="mr-2 h-4 w-4" />
          新建知识库
        </Button>
      </header>
      {bases.isLoading && <p role="status">正在打开知识空间…</p>}
      {bases.isError && (
        <div role="alert">
          知识库加载失败。
          <Button variant="outline" onClick={() => bases.refetch()}>
            重新加载
          </Button>
        </div>
      )}
      {!current && !bases.isLoading && !bases.isError && (
        <section aria-label="知识库列表" className="kb-library">
          <div className="workspace-list-toolbar">
            <span className="workspace-list-tab">
              我的知识库 <span>{bases.data?.items.length || 0}</span>
            </span>
            <label className="workspace-search">
              <Search size={16} />
              <input
                aria-label="搜索知识库"
                placeholder="搜索知识库名称或简介"
                value={baseQuery}
                onChange={(e) => setBaseQuery(e.target.value)}
              />
            </label>
          </div>
          {searchParams.get("base") && (
            <p role="status" className="text-muted-foreground mb-4 text-sm">
              该知识库不存在或已移除，请选择其他知识库。
            </p>
          )}
          <div className="kb-library-grid">
            {visibleBases?.map((base, i) => (
              <Link
                key={base.id}
                href={`/knowledge?base=${encodeURIComponent(base.id)}`}
                className="kb-library-card"
                style={{ "--kb-tone": ["145", "210", "265", "30"][i % 4] } as React.CSSProperties}
              >
                <div className="kb-card-heading">
                  <span className="kb-card-icon">
                    <FolderOpen size={24} strokeWidth={1.65} />
                  </span>
                  <span className="kb-private-label">个人知识库</span>
                  <ArrowUpRight size={16} className="kb-card-arrow" />
                </div>
                <h2>{base.name}</h2>
                <p>{base.description || "添加文档、知识条目或常见问答，随时检索与提问。"}</p>
                <div className="kb-card-footer">
                  <span>
                    <FileText size={14} />
                    {base.document_count} 份资料
                  </span>
                  <span>
                    <Database size={14} />
                    {base.chunk_count} 个片段
                  </span>
                </div>
              </Link>
            ))}
            {!baseQuery && (
              <button className="kb-create-card" onClick={() => setCreateOpen(true)}>
                <span>
                  <Plus size={24} />
                </span>
                <strong>创建知识库</strong>
                <p>为新的主题建立知识空间</p>
              </button>
            )}
          </div>
          {baseQuery && visibleBases?.length === 0 && (
            <div className="workspace-empty">
              <Search size={28} />
              <h2>没有找到匹配的知识库</h2>
              <p>试试其他关键词，或清除搜索条件。</p>
              <Button variant="outline" onClick={() => setBaseQuery("")}>
                清除搜索
              </Button>
            </div>
          )}
        </section>
      )}
      <div>
        {current && (
          <section className="kb-detail-panel min-w-0">
            <Tabs defaultValue="files" key={current.id}>
              <div className="kb-detail-summary mb-5 flex flex-wrap items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-muted-foreground mt-2 text-xs" aria-live="polite">
                    {ready} 份可检索 · {processing} 份处理中 · {failed} 份失败
                  </p>
                </div>
                {ready ? (
                  <Button asChild className="mint-action">
                    <Link href={`/chat?knowledge=${current.id}`}>
                      开始提问
                      <ArrowUpRight className="ml-1 h-4 w-4" />
                    </Link>
                  </Button>
                ) : (
                  <Button disabled>资料就绪后可提问</Button>
                )}
              </div>
              <TabsList
                className="workspace-tabs mb-5 w-full justify-start"
                aria-label="知识库功能"
              >
                <TabsTrigger value="files" className="flex-1 sm:flex-none">
                  资料管理
                </TabsTrigger>
                <TabsTrigger value="retrieval" className="flex-1 sm:flex-none">
                  检索测试
                </TabsTrigger>
              </TabsList>
              <TabsContent value="files" className="mt-0 space-y-3 sm:space-y-5">
                <div className="console-kb-toolbar">
                  <Button
                    onClick={() => input.current?.click()}
                    disabled={busy}
                    className="mint-action"
                  >
                    <Upload className="mr-1 h-4 w-4" />
                    上传文件
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setEditor({ baseId: current.id, kind: "manual" })}
                  >
                    写知识
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setEditor({ baseId: current.id, kind: "faq" })}
                  >
                    新建 FAQ
                  </Button>
                  <details className="console-processing-tools">
                    <summary>处理设置与预览</summary>
                    <div>
                      <ChunkPreview
                        key={`${userId}-${current.id}`}
                        base={current}
                        onUploaded={refresh}
                      />
                      <ChunkingSettings key={current.id} base={current} onSaved={refresh} />
                    </div>
                  </details>
                </div>
                <details className="console-upload-help">
                  <summary>拖拽上传与格式说明</summary>
                  <button
                    disabled={busy}
                    onClick={() => input.current?.click()}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault();
                      if (!busy) void upload(e.dataTransfer.files);
                    }}
                    className="upload-zone flex w-full flex-col items-center gap-2 rounded-xl border border-dashed p-5 text-sm"
                  >
                    <Upload className="text-brand h-6 w-6" />
                    <span>{busy ? "正在上传，请稍候…" : "拖拽文件到这里，或点击上传"}</span>
                    <span className="text-muted-foreground text-xs">
                      PDF · DOCX · TXT · Markdown · CSV，单文件最大 10 MB
                    </span>
                  </button>
                </details>
                <input
                  ref={input}
                  type="file"
                  multiple
                  accept=".pdf,.docx,.txt,.md,.csv"
                  className="hidden"
                  onChange={(e) => void upload(e.target.files)}
                  aria-label="上传知识库文件"
                />
                {uploads?.base === current.id && (
                  <div className="rounded-xl border p-4" aria-live="polite">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm">{busy ? "正在逐个上传…" : "本次上传结果"}</p>
                      {!busy && (
                        <Button variant="ghost" size="sm" onClick={() => setUploads(null)}>
                          收起结果
                        </Button>
                      )}
                    </div>
                    <ul className="mt-2 max-h-44 space-y-2 overflow-y-auto">
                      {uploads.items.map((item, index) => (
                        <li key={index} className="flex flex-wrap justify-between gap-2 text-xs">
                          <span className="min-w-0 break-all">{item.name}</span>
                          <span className={item.failed ? "text-destructive" : "text-brand"}>
                            {item.result}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="flex flex-col gap-3 sm:flex-row">
                  <Input
                    aria-label="搜索资料标题"
                    placeholder="搜索资料标题…"
                    value={fileQuery}
                    onChange={(e) => setFileQuery(e.target.value)}
                    className="min-w-0 flex-1"
                  />
                  <select
                    aria-label="筛选资料类型"
                    value={kindFilter}
                    onChange={(e) => setKindFilter(e.target.value)}
                    className="bg-background h-10 rounded-lg border px-3 text-sm"
                  >
                    <option value="all">全部类型</option>
                    <option value="file">上传文件</option>
                    <option value="manual">手动知识</option>
                    <option value="faq">FAQ</option>
                  </select>
                  <select
                    aria-label="筛选资料状态"
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="bg-background h-10 rounded-lg border px-3 text-sm"
                  >
                    <option value="all">全部状态（{docs.data?.length || 0}）</option>
                    <option value="ready">可检索（{ready}）</option>
                    <option value="active">处理中（{processing}）</option>
                    <option value="failed">失败（{failed}）</option>
                  </select>
                </div>
                {docs.isLoading && <p role="status">加载资料…</p>}
                {docs.isError && <p role="alert">资料加载失败，请刷新页面重试。</p>}
                <ul aria-label="知识库资料" className="divide-border divide-y">
                  {filteredDocs?.map((d) => (
                    <li key={d.id} className="console-document-row">
                      <div className="flex items-start gap-3">
                        <FileText className="text-muted-foreground mt-1 h-5 w-5 shrink-0" />
                        <div className="console-document-info min-w-0 flex-1">
                          <p className="truncate text-sm font-medium" title={d.title || d.filename}>
                            {d.title || d.filename}
                          </p>
                          <div className="console-doc-meta mt-2 flex flex-wrap items-center gap-2 text-xs">
                            <span className="text-muted-foreground rounded border px-2 py-1">
                              {d.source_kind === "faq"
                                ? "FAQ"
                                : d.source_kind === "manual"
                                  ? "手动知识"
                                  : "上传文件"}
                            </span>
                            <span className={`status-pill status-${d.status}`}>
                              {stages[d.status] || d.status}
                            </span>
                            <span className="text-muted-foreground">
                              {(d.size / 1024).toFixed(1)} KB
                              {d.status === "ready" ? ` · ${d.chunk_count} 片段` : ""}
                            </span>
                          </div>
                          {d.error && (
                            <p role="alert" className="mt-2 text-xs leading-5 text-red-300">
                              {d.error}
                            </p>
                          )}
                          {d.parse_report && <ParseReport report={d.parse_report} />}
                          {d.status === "ready" && (
                            <details className="text-muted-foreground mt-3 text-xs leading-6">
                              <summary className="cursor-pointer">处理详情</summary>
                              <p>
                                {d.chunking_config
                                  ? `已用配置：长度 ${d.chunking_config.chunk_size} · 重叠 ${d.chunking_config.chunk_overlap}`
                                  : "旧索引尚未记录分块配置"}
                              </p>
                              {d.source_kind === "faq" && (
                                <p>每段保留问题；答案分段的重叠不超过可用长度的三分之一。</p>
                              )}
                              <p>重新处理期间暂停检索；历史引用保留回答时的原文。</p>
                            </details>
                          )}
                          {d.status === "ready" &&
                            (!d.chunking_config ||
                              d.chunking_config.chunk_size !==
                                (current.chunking_config?.chunk_size ?? 450) ||
                              d.chunking_config.chunk_overlap !==
                                (current.chunking_config?.chunk_overlap ?? 65)) && (
                              <p className="mt-2 text-xs text-amber-200">
                                与当前分块设置不同，重新处理后生效。
                              </p>
                            )}
                          {d.status === "ready" &&
                            d.filename.toLowerCase().endsWith(".pdf") &&
                            !d.parse_report && (
                              <p className="text-muted-foreground mt-3 text-xs">
                                暂无页面提取报告，可重新处理获取。
                              </p>
                            )}
                          <DocumentActions
                            document={d}
                            baseId={current.id}
                            busy={busy}
                            onEdit={() =>
                              setEditor({
                                baseId: current.id,
                                kind: d.source_kind as "manual" | "faq",
                                documentId: d.id,
                              })
                            }
                            onPreview={() => void showChunks(d)}
                            onRetry={async () => {
                              setBusy(true);
                              try {
                                await api(`documents/${d.id}/retry`, { method: "POST" });
                                await refresh();
                              } catch (e) {
                                fail(e);
                              } finally {
                                setBusy(false);
                              }
                            }}
                            onRemove={() =>
                              setRemoval({ path: `documents/${d.id}`, name: d.title || d.filename })
                            }
                          />
                        </div>
                      </div>
                      {active.has(d.status) && (
                        <ol
                          className="text-muted-foreground mt-4 flex flex-wrap gap-3 text-[10px]"
                          aria-label="文件处理流程"
                        >
                          {["pending", "parsing", "chunking", "embedding", "ready"].map((s) => (
                            <li key={s} className={d.status === s ? "text-brand" : ""}>
                              {stages[s]}
                            </li>
                          ))}
                        </ol>
                      )}
                    </li>
                  ))}
                </ul>
                {docs.data?.length === 0 && (
                  <p className="text-muted-foreground py-6 text-center text-sm">
                    还没有资料。上传文件、写一条知识或添加 FAQ，即可开始入库。
                  </p>
                )}
                {!!docs.data?.length && filteredDocs?.length === 0 && (
                  <div className="text-muted-foreground py-6 text-center text-sm">
                    没有符合筛选条件的资料。
                    <Button
                      variant="ghost"
                      onClick={() => {
                        setFileQuery("");
                        setStatusFilter("all");
                        setKindFilter("all");
                      }}
                    >
                      清除筛选
                    </Button>
                  </div>
                )}
                <details className="border-t pt-4 text-xs">
                  <summary className="text-muted-foreground cursor-pointer">知识库管理</summary>
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                    <p className="text-muted-foreground">
                      删除知识库将移除其中的所有原文和检索片段。
                    </p>
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-destructive"
                      aria-label={`删除知识库 ${current.name}`}
                      onClick={() =>
                        setRemoval({ path: `bases/${current.id}`, name: current.name })
                      }
                    >
                      删除知识库
                    </Button>
                  </div>
                </details>
              </TabsContent>
              <TabsContent value="retrieval" className="mt-0">
                <RetrievalTester base={current} readyCount={ready} />
              </TabsContent>
            </Tabs>
          </section>
        )}
      </div>
      {editor && (
        <EntryEditor
          key={`${editor.baseId}-${editor.documentId || editor.kind}`}
          {...editor}
          onClose={() => setEditor(null)}
          onSaved={(doc) => {
            cache.setQueryData<KnowledgeDocument[]>(
              ["knowledge-documents", userId, editor.baseId],
              (previous = []) =>
                previous.some((item) => item.id === doc.id)
                  ? previous.map((item) => (item.id === doc.id ? doc : item))
                  : [doc, ...previous],
            );
            setEditor(null);
            setFileQuery("");
            setStatusFilter("all");
            setKindFilter("all");
            toast.success(doc.status === "pending" ? "已保存，正在生成检索索引" : "已保存");
            void refresh().catch(fail);
          }}
        />
      )}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新建知识库</DialogTitle>
            <DialogDescription>为一个项目、主题或学习计划，留出独立的知识空间。</DialogDescription>
          </DialogHeader>
          <form onSubmit={create} className="space-y-4">
            <label htmlFor="kb-name" className="block space-y-2 text-sm">
              <span>名称</span>
              <Input
                id="kb-name"
                required
                maxLength={100}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="例如：产品资料、学习笔记"
              />
            </label>
            <label htmlFor="kb-description" className="block space-y-2 text-sm">
              <span>简介（可选）</span>
              <Input
                id="kb-description"
                maxLength={1000}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </label>
            <Button disabled={busy || !name.trim()} type="submit">
              {busy ? "创建中…" : "创建知识库"}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
      <Dialog open={!!removal} onOpenChange={(open) => !open && setRemoval(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除「{removal?.name}」？</DialogTitle>
            <DialogDescription>原文及检索片段将一并删除，此操作无法撤销。</DialogDescription>
          </DialogHeader>
          <Button
            variant="destructive"
            disabled={busy}
            onClick={async () => {
              if (!removal) return;
              setBusy(true);
              try {
                await api(removal.path, { method: "DELETE" });
                setRemoval(null);
                setPreview(null);
                await refresh();
              } catch (e) {
                fail(e);
              } finally {
                setBusy(false);
              }
            }}
          >
            确认删除
          </Button>
        </DialogContent>
      </Dialog>
      <Dialog
        open={!!preview && preview.base === current?.id}
        onOpenChange={(open) => {
          if (!open) {
            chunkRequest.current?.abort();
            setPreview(null);
          }
        }}
      >
        <DialogContent className="max-h-[85dvh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{preview?.filename}</DialogTitle>
            <DialogDescription>索引中的原文片段，按文档顺序排列。</DialogDescription>
          </DialogHeader>
          {chunksLoading && (
            <p role="status" className="text-muted-foreground text-sm">
              正在加载分块…
            </p>
          )}
          {chunkError && (
            <p role="alert" className="text-destructive text-sm">
              {chunkError}
            </p>
          )}
          {preview?.items.slice(chunkPage * 10, (chunkPage + 1) * 10).map((c) => (
            <article key={c.id} className="rounded-xl border p-4">
              <p className="text-brand mb-2 text-xs">
                片段 {c.position + 1}
                {c.page ? ` · 第 ${c.page} 页` : ""}
              </p>
              <p className="text-sm leading-7 whitespace-pre-wrap">{c.content}</p>
            </article>
          ))}
          {preview && preview.items.length > 10 && (
            <div className="bg-background sticky bottom-0 flex items-center justify-between border-t py-3">
              <Button
                variant="outline"
                disabled={chunkPage === 0}
                onClick={() => setChunkPage(chunkPage - 1)}
              >
                上一页
              </Button>
              <span className="text-xs">
                {chunkPage + 1} / {Math.ceil(preview.items.length / 10)}
              </span>
              <Button
                variant="outline"
                disabled={(chunkPage + 1) * 10 >= preview.items.length}
                onClick={() => setChunkPage(chunkPage + 1)}
              >
                下一页
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
