import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ChunkPreview } from "./chunk-preview";

const base = { id: "base-a", name: "资料库", description: "", document_count: 0, chunk_count: 0, chunking_config: { chunk_size: 300, chunk_overlap: 0 } };
const result = { chunk_count: 1, min_length: 2, max_length: 2, mean_length: 2, truncated: false, parse_report: null, preview_token: "signed-receipt", items: [{ position: 0, content: "原文", page: null }], chunking_config: base.chunking_config };
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
function choose() { fireEvent.change(screen.getByLabelText("选择分块预览文件"), { target: { files: [new File(["原文"], "guide.txt", { type: "text/plain" })] } }); }
it("invalidates the preview after editing parameters and submits the confirmed receipt", async () => {
  const fetch = vi.fn(async () => new Response(JSON.stringify(result)));
  vi.stubGlobal("fetch", fetch);
  const saved = vi.fn(async () => {});
  render(<ChunkPreview base={base} onUploaded={saved} />);
  choose();
  expect(screen.getByLabelText("片段长度（字符）")).toHaveValue(300);
  fireEvent.click(screen.getByRole("button", { name: "生成预览" }));
  await screen.findByRole("button", { name: "确认并开始入库" });
  fireEvent.change(screen.getByLabelText("片段长度（字符）"), { target: { value: "420" } });
  expect(screen.queryByRole("button", { name: "确认并开始入库" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "生成预览" }));
  fireEvent.click(await screen.findByRole("button", { name: "确认并开始入库" }));
  await act(async () => {});
  expect(fetch.mock.calls).toHaveLength(3);
  const calls = fetch.mock.calls as unknown as [string, RequestInit][];
  expect(calls[2]![0]).toBe("/api/knowledge/bases/base-a/documents");
  expect((calls[2]![1].body as FormData).get("preview_token")).toBe("signed-receipt");
  expect(saved).toHaveBeenCalledOnce();
});
it("ignores an old response after closing and selecting a different file", async () => {
  let resolve!: (response: Response) => void;
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((r) => { resolve = r; })));
  render(<ChunkPreview base={base} onUploaded={async () => {}} />);
  choose(); fireEvent.click(screen.getByRole("button", { name: "生成预览" }));
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  choose();
  await act(async () => resolve(new Response(JSON.stringify(result))));
  expect(screen.queryByRole("button", { name: "确认并开始入库" })).toBeNull();
  expect(screen.getByRole("button", { name: "生成预览" })).toBeEnabled();
});
it("keeps parse failures out of the confirmation flow", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "请先 OCR" }), { status: 400 })));
  render(<ChunkPreview base={base} onUploaded={async () => {}} />);
  choose(); fireEvent.click(screen.getByRole("button", { name: "生成预览" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("请先 OCR");
  expect(screen.queryByRole("button", { name: "确认并开始入库" })).toBeNull();
});
