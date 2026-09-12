import type { PDFParseReport } from "@/lib/knowledge";

export function ParseReport({ report, snapshot = false }: { report: PDFParseReport; snapshot?: boolean }) {
  const incomplete = report.empty_text_pages.length > 0 || report.suspected_scan_pages.length > 0;
  return (
    <details className="mt-3 rounded-lg border p-3 text-xs leading-6">
      <summary className={`cursor-pointer ${incomplete ? "text-amber-200" : "text-muted-foreground"}`}>
        {snapshot ? "回答时的文字提取情况" : "文字提取情况"}：{report.text_pages} / {report.total_pages} 页有文字
        {incomplete && " · 部分页面需检查"}
      </summary>
      <div className="text-muted-foreground mt-2 max-h-48 space-y-2 overflow-y-auto break-words">
        <p>页数仅表示提取到文字，不代表全文完整。图片、图表及公式内容请对照原文件核实。</p>
        {report.empty_text_pages.length > 0 && <p>未提取到文字：第 {report.empty_text_pages.join("、")} 页。可能是空白、图片或扫描页面，这些页面未进入文字检索。</p>}
        {report.suspected_scan_pages.length > 0 && <p>疑似扫描或图片为主：第 {report.suspected_scan_pages.join("、")} 页。仅有少量文字或没有文字；如包含正文，请先 OCR 再上传。</p>}
        {report.two_column_pages.length > 0 && <p>按双栏顺序整理：第 {report.two_column_pages.join("、")} 页。复杂版式仍需对照原文核实。</p>}
      </div>
    </details>
  );
}
