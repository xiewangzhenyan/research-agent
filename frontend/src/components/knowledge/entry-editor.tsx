"use client";

import { useEffect, useId, useState } from "react";
import { Button, Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, Input } from "@/components/ui";
import { knowledgeRequest, KnowledgeRequestError, type EntryRead, type KnowledgeDocument, type KnowledgeEntry } from "@/lib/knowledge";

export function EntryEditor({ baseId, kind, documentId, onClose, onSaved }: {
  baseId: string; kind: "manual" | "faq"; documentId?: string;
  onClose: () => void; onSaved: (document: KnowledgeDocument) => void;
}) {
  const id = useId();
  const initial: KnowledgeEntry = kind === "manual" ? { kind, title: "", content: "" } : { kind, question: "", answer: "" };
  const [draft, setDraft] = useState<KnowledgeEntry>(initial);
  const [original, setOriginal] = useState(JSON.stringify(initial));
  const [revision, setRevision] = useState<number>();
  const [loaded, setLoaded] = useState(!documentId);
  const [reload, setReload] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [discard, setDiscard] = useState(false);
  const dirty = JSON.stringify(draft) !== original;
  const faq = draft.kind === "faq";
  useEffect(() => {
    if (!documentId) return;
    const controller = new AbortController();
    setLoaded(false); setError(""); setConflict(false);
    knowledgeRequest<EntryRead>(`documents/${documentId}/entry`, { signal: controller.signal }).then((data) => {
      if (controller.signal.aborted) return;
      setDraft(data.entry); setOriginal(JSON.stringify(data.entry)); setRevision(data.revision); setLoaded(true);
    }).catch((e) => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "加载失败"); });
    return () => controller.abort();
  }, [documentId, reload]);
  useEffect(() => {
    if (!dirty) return;
    const guard = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);
  function close() {
    if (saving) return;
    if (dirty) setDiscard(true); else onClose();
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!loaded || saving || conflict) return;
    setSaving(true); setError("");
    try {
      const doc = await knowledgeRequest<KnowledgeDocument>(documentId ? `documents/${documentId}/entry` : `bases/${baseId}/entries`, {
        method: documentId ? "PUT" : "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(documentId ? { ...draft, revision } : draft),
      });
      onSaved(doc);
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败，当前修改已保留");
      setConflict(e instanceof KnowledgeRequestError && e.code === "REVISION_CONFLICT");
    } finally { setSaving(false); }
  }
  return <Dialog open onOpenChange={(open) => { if (!open) close(); }}>
    <DialogContent className="flex max-h-[88dvh] max-w-2xl flex-col gap-4 overflow-hidden" onPointerDownOutside={(e) => e.preventDefault()}>
      <DialogHeader className="pr-6">
        <DialogTitle>{documentId ? "编辑" : "新建"}{faq ? " FAQ" : "手动知识"}</DialogTitle>
        <DialogDescription>保存后自动分块并生成索引。处理期间暂停检索，历史回答保留当时引用的原文。</DialogDescription>
      </DialogHeader>
      {!loaded && !error && <p role="status" className="text-sm">正在加载内容…</p>}
      <form onSubmit={save} className="flex min-h-0 flex-1 flex-col gap-4">
        <fieldset disabled={!loaded || saving} className="min-h-0 space-y-4 overflow-y-auto overscroll-contain pr-1">
          <label htmlFor={`${id}-title`} className="block space-y-2 text-sm">
            <span>{faq ? "问题" : "标题"}</span>
            <Input id={`${id}-title`} required maxLength={150} value={draft.kind === "faq" ? draft.question : draft.title} onChange={(e) => setDraft(draft.kind === "faq" ? { ...draft, question: e.target.value } : { ...draft, title: e.target.value })} placeholder={faq ? "例如：出差住宿如何报销？" : "例如：设备使用规范"} />
          </label>
          <div className="space-y-2 text-sm">
            <label htmlFor={`${id}-body`}>{faq ? "标准答案" : "正文"}</label>
            <textarea id={`${id}-body`} aria-describedby={`${id}-hint`} required maxLength={faq ? 10000 : 20000} rows={10} value={draft.kind === "faq" ? draft.answer : draft.content} onChange={(e) => setDraft(draft.kind === "faq" ? { ...draft, answer: e.target.value } : { ...draft, content: e.target.value })} className="bg-background focus-visible:ring-ring min-h-40 w-full resize-y rounded-lg border p-3 text-sm leading-7 focus-visible:ring-2 focus-visible:outline-none" placeholder={faq ? "写下可直接作为依据的答案，包含适用条件和限制。" : "粘贴或编写资料正文，支持保存 Markdown 文本。"} />
            <span id={`${id}-hint`} className="text-muted-foreground flex flex-wrap justify-between gap-2 text-xs"><span>{faq ? "长答案会分段，每段保留对应问题。" : "内容按当前知识库的分块设置处理。"}</span><span>{(draft.kind === "faq" ? draft.answer : draft.content).length} / {faq ? 10000 : 20000}</span></span>
          </div>
        </fieldset>
        <div className="shrink-0 space-y-3 border-t pt-4">
          {error && <p role="alert" className="text-destructive break-words text-sm leading-6">{error}</p>}
          {!loaded && error && <Button type="button" variant="outline" onClick={() => setReload(reload + 1)}>重新加载内容</Button>}
          {conflict && <Button type="button" variant="outline" onClick={() => setReload(reload + 1)}>放弃当前修改并加载最新版本</Button>}
          {discard ? <div className="space-y-3" role="alert"><p className="text-sm">尚有未保存的修改，是否放弃？</p><div className="flex flex-wrap gap-2"><Button type="button" onClick={() => setDiscard(false)}>继续编辑</Button><Button type="button" variant="outline" onClick={onClose}>放弃修改并关闭</Button></div></div> : <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-muted-foreground text-xs">{documentId && revision ? `版本 ${revision} · ` : ""}{dirty ? "有未保存的修改" : "内容未修改"}</span>
            <div className="flex gap-2"><Button type="button" variant="outline" disabled={saving} onClick={close}>取消</Button><Button type="submit" className="mint-action" disabled={!loaded || saving || conflict || !dirty || !(draft.kind === "faq" ? draft.question.trim() && draft.answer.trim() : draft.title.trim() && draft.content.trim())}>{saving ? "正在保存…" : "保存并入库"}</Button></div>
          </div>}
        </div>
      </form>
    </DialogContent>
  </Dialog>;
}
