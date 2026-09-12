"use client";

import { useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";
import { Button, Input, Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui";
import { ParseReport } from "./parse-report";
import { knowledgeRequest, type KnowledgeBase, type ChunkPreviewResult } from "@/lib/knowledge";

export function ChunkPreview({ base, onUploaded }: { base: KnowledgeBase; onUploaded: () => Promise<void> }) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const request = useRef<AbortController | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [size, setSize] = useState("450");
  const [overlap, setOverlap] = useState("65");
  const [result, setResult] = useState<ChunkPreviewResult | null>(null);
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => () => { request.current?.abort(); }, []);
  function close() {
    request.current?.abort(); request.current = null;
    setFile(null); setResult(null); setError(""); setBusy(false);
  }
  async function preview(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    setResult(null); setError(""); setPage(0);
    if (Number(overlap) * 2 >= Number(size)) {
      setError("重叠长度必须小于片段长度的一半"); return;
    }
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    const form = new FormData();
    form.set("file", file); form.set("chunk_size", size); form.set("chunk_overlap", overlap);
    setBusy(true);
    try {
      const response = await knowledgeRequest<ChunkPreviewResult>(`bases/${base.id}/preview`, {
        method: "POST", body: form, signal: controller.signal,
      });
      if (!controller.signal.aborted) setResult(response);
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "预览失败");
    } finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function upload() {
    if (!file || !result) return;
    setUploading(true); setError("");
    const form = new FormData(); form.set("file", file); form.set("preview_token", result.preview_token);
    try {
      await knowledgeRequest(`bases/${base.id}/documents`, { method: "POST", body: form });
      close();
      toast.success("已按预览参数提交入库，可在文件列表查看处理状态");
      await onUploaded();
    } catch (e) { setError(e instanceof Error ? e.message : "提交失败"); }
    finally { setUploading(false); }
  }
  return <>
    <Button variant="outline" size="sm" onClick={() => input.current?.click()}>入库前预览</Button>
    <input ref={input} type="file" accept=".pdf,.docx,.txt,.md,.csv" className="hidden" aria-label="选择分块预览文件" onChange={(e) => {
      const selected = e.target.files?.[0]; e.target.value = "";
      if (!selected) return;
      if (!selected.size || selected.size > 10 * 1024 * 1024) { toast.error("文件不能为空，且不能超过 10 MB"); return; }
      setSize(String(base.chunking_config?.chunk_size ?? 450));
      setOverlap(String(base.chunking_config?.chunk_overlap ?? 65));
      setResult(null); setError(""); setPage(0); setFile(selected);
    }} />
    <Dialog open={!!file} onOpenChange={(open) => { if (!open && !uploading) close(); }}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader><DialogTitle>入库前分块预览</DialogTitle><DialogDescription className="break-all">{base.name} · {file?.name}</DialogDescription></DialogHeader>
        <p className="text-muted-foreground text-xs leading-6">预览只解析和分块，尚未入库。确认后按本次参数生成向量，不修改知识库默认设置。预览确认有效期为 15 分钟。</p>
        <form onSubmit={preview} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <label htmlFor={`${id}-size`} className="space-y-2 text-sm">片段长度（字符）
              <Input id={`${id}-size`} type="number" min={256} max={500} step={1} required disabled={busy || uploading} value={size} onChange={(e) => { setSize(e.target.value); setResult(null); }} />
            </label>
            <label htmlFor={`${id}-overlap`} className="space-y-2 text-sm">重叠长度（字符）
              <Input id={`${id}-overlap`} type="number" min={0} max={128} step={1} required disabled={busy || uploading} value={overlap} onChange={(e) => { setOverlap(e.target.value); setResult(null); }} />
            </label>
          </div>
          <p className="text-muted-foreground text-xs">长度 256–500；重叠 0–128 且小于长度的一半。表格按行保留表头，不跨行重叠。</p>
          <Button type="submit" variant="outline" disabled={busy || uploading}>{busy ? "正在解析与分块…" : "生成预览"}</Button>
        </form>
        {error && <p role="alert" className="text-destructive text-sm">{error}</p>}
        {busy && <p role="status" className="text-muted-foreground text-sm">正在处理文件，通常需要几秒钟…</p>}
        {result && <div className="space-y-4">
          <p role="status" className="text-sm">共 {result.chunk_count} 个片段 · 最短 {result.min_length} / 最长 {result.max_length} / 平均 {result.mean_length} 字符</p>
          {result.parse_report && <ParseReport report={result.parse_report} />}
          {result.truncated && <p className="text-muted-foreground text-xs">仅展示前 {result.items.length} 个片段；统计覆盖全部片段，正式入库将处理全部内容。</p>}
          {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users need to focus and scroll the bounded preview region. */}
          <div className="max-h-[38dvh] space-y-3 overflow-y-auto pr-1" tabIndex={0} role="region" aria-label="预览片段">
            {result.items.slice(page * 10, (page + 1) * 10).map((chunk) => <article key={chunk.position} className="rounded-xl border p-4">
              <p className="text-muted-foreground mb-2 text-xs">片段 {chunk.position + 1} · {Array.from(chunk.content).length} 字符{chunk.page ? ` · 第 ${chunk.page} 页` : ""}{chunk.location?.section ? ` · ${chunk.location.section}` : ""}{chunk.location?.table ? ` · 表 ${chunk.location.table}` : ""}{chunk.location?.row ? ` · 行 ${chunk.location.row}` : ""}</p>
              <p className="whitespace-pre-wrap break-words text-sm leading-7">{chunk.content}</p>
            </article>)}
          </div>
          {result.items.length > 10 && <div className="flex items-center justify-between gap-2">
            <Button variant="ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>上一页</Button>
            <span className="text-xs">{page + 1} / {Math.ceil(result.items.length / 10)}</span>
            <Button variant="ghost" disabled={(page + 1) * 10 >= result.items.length} onClick={() => setPage(page + 1)}>下一页</Button>
          </div>}
          <Button className="mint-action w-full sm:w-auto" onClick={upload} disabled={uploading}>{uploading ? "正在提交…" : "确认并开始入库"}</Button>
        </div>}
      </DialogContent>
    </Dialog>
  </>;
}
