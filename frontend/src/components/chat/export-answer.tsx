"use client";

import { Download, Loader2 } from "lucide-react";
import { useLocale } from "next-intl";
import { useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui";
import { saveBlob, useFileDownload } from "@/hooks/use-file-download";

export function ExportAnswer({
  content,
  messageId,
  saved,
}: {
  content: string;
  messageId: string;
  saved: boolean;
}) {
  const zh = useLocale() === "zh";
  const [open, setOpen] = useState(false);
  const { download, busy } = useFileDownload(messageId);
  const office = saved && /^[0-9a-f-]{36}$/i.test(messageId);
  const formats = [
    { id: "md", label: "Markdown", hint: zh ? "保留原始正文" : "Original text" },
    { id: "docx", label: "Word", hint: zh ? "标题、正文与表格" : "Headings and tables" },
    { id: "xlsx", label: "Excel", hint: zh ? "表格拆为工作表" : "Tables as worksheets" },
    {
      id: "pptx",
      label: "PowerPoint",
      hint: zh ? "按章节生成文字幻灯片" : "Text slides by section",
    },
  ];
  const exportFile = (format: string) => {
    setOpen(false);
    const name = `${zh ? "对话回答" : "response"}-${messageId.slice(0, 8)}.${format}`;
    if (format === "md")
      saveBlob(new Blob([content], { type: "text/markdown;charset=utf-8" }), name);
    else
      void download(`/api/chat/messages/${messageId}/export`, name, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ format }),
      });
  };
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={!!busy}
          aria-label={zh ? "导出回答" : "Export answer"}
          title={zh ? "导出回答" : "Export answer"}
          className="text-muted-foreground hover:text-foreground hover:bg-muted inline-flex h-8 w-8 items-center justify-center rounded-lg"
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
          ) : (
            <Download className="h-4 w-4" />
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" side="top" className="w-64 rounded-2xl p-1.5">
        {formats.map((format) => (
          <button
            key={format.id}
            type="button"
            disabled={!!busy || (format.id !== "md" && !office)}
            onClick={() => exportFile(format.id)}
            aria-label={`${zh ? "下载" : "Download"} ${format.label}`}
            className="hover:bg-muted flex min-h-12 w-full flex-col rounded-lg px-3 py-2 text-left disabled:opacity-40"
          >
            <span className="text-sm">
              {format.label} <span className="text-muted-foreground text-xs">.{format.id}</span>
            </span>
            <span className="text-muted-foreground text-xs">{format.hint}</span>
          </button>
        ))}
        <p className="text-muted-foreground px-3 py-2 text-xs leading-5">
          {zh
            ? "Office 导出保留引用来源；公式以 LaTeX 文本保留，暂不转换为可编辑公式。"
            : "Office exports include sources. LaTeX is preserved as text, not editable equations."}
        </p>
      </PopoverContent>
    </Popover>
  );
}
