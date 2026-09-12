"use client";

import { useId, useState } from "react";
import { toast } from "sonner";
import { Button, Input, Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui";
import { knowledgeRequest, type KnowledgeBase } from "@/lib/knowledge";

export function ChunkingSettings({ base, onSaved }: { base: KnowledgeBase; onSaved: () => Promise<void> }) {
  const fieldId = useId();
  const [open, setOpen] = useState(false);
  const [size, setSize] = useState("450");
  const [overlap, setOverlap] = useState("65");
  const [saving, setSaving] = useState(false);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    const config = { chunk_size: Number(size), chunk_overlap: Number(overlap) };
    if (config.chunk_overlap * 2 >= config.chunk_size) {
      toast.error("重叠长度必须小于片段长度的一半");
      return;
    }
    setSaving(true);
    try {
      await knowledgeRequest(`bases/${base.id}/chunking-config`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config),
      });
      await onSaved();
      setOpen(false);
      toast.success("分块设置已保存，已有文件需重新处理后生效");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败，请重试");
    } finally { setSaving(false); }
  }
  return <>
    <Button variant="outline" size="sm" onClick={() => {
      setSize(String(base.chunking_config?.chunk_size ?? 450));
      setOverlap(String(base.chunking_config?.chunk_overlap ?? 65));
      setOpen(true);
    }}>分块设置</Button>
    <Dialog open={open} onOpenChange={(value) => { if (!saving) setOpen(value); }}>
      <DialogContent>
        <DialogHeader><DialogTitle>分块设置</DialogTitle><DialogDescription>为“{base.name}”设置文字片段的长度与重叠范围。</DialogDescription></DialogHeader>
        <form onSubmit={save} className="space-y-5">
          <label htmlFor={`${fieldId}-size`} className="block space-y-2 text-sm">片段长度（字符）
            <Input id={`${fieldId}-size`} type="number" min={256} max={500} step={1} required value={size} onChange={(event) => setSize(event.target.value)} />
          </label>
          <label htmlFor={`${fieldId}-overlap`} className="block space-y-2 text-sm">重叠长度（字符）
            <Input id={`${fieldId}-overlap`} type="number" min={0} max={128} step={1} required value={overlap} onChange={(event) => setOverlap(event.target.value)} />
          </label>
          <p className="text-muted-foreground text-xs leading-6">当前支持 256–500 字符，重叠为 0–128 字符且小于片段长度的一半。片段会尽量在段落或句子边界结束；表格逐行保留表头，不跨行重叠。</p>
          <p className="text-muted-foreground text-xs leading-6">直接上传和重新处理在任务开始时使用当前设置；经预览确认的上传使用预览参数。修改设置不会自动重建已有文件；需要在文件列表点击“重新处理”。历史引用仍保留回答时的原文。</p>
          <Button type="submit" disabled={saving}>{saving ? "正在保存…" : "保存分块设置"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  </>;
}
