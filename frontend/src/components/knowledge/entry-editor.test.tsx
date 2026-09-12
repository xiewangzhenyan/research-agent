import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { EntryEditor } from "./entry-editor";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("creates a structured FAQ and protects unsaved edits when closing", async () => {
  const fetch = vi.fn(
    async () => new Response(JSON.stringify({ id: "new", status: "pending", source_kind: "faq" })),
  );
  vi.stubGlobal("fetch", fetch);
  const close = vi.fn(),
    saved = vi.fn();
  render(<EntryEditor baseId="base" kind="faq" onClose={close} onSaved={saved} />);
  fireEvent.change(screen.getByLabelText("问题"), { target: { value: "如何报销？" } });
  fireEvent.change(screen.getByLabelText("标准答案"), { target: { value: "每晚620元。" } });
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(close).not.toHaveBeenCalled();
  expect(screen.getByText(/尚有未保存的修改/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  fireEvent.click(screen.getByRole("button", { name: "保存并入库" }));
  await waitFor(() => expect(saved).toHaveBeenCalled());
  const call = fetch.mock.calls[0] as unknown as [string, RequestInit];
  expect(call[0]).toBe("/api/knowledge/bases/base/entries");
  expect(JSON.parse(call[1].body as string)).toEqual({
    kind: "faq",
    question: "如何报销？",
    answer: "每晚620元。",
  });
});
it("keeps conflicting edits visible and requires explicit reload before another save", async () => {
  const fetch = vi.fn(async (_url: string, options?: RequestInit) =>
    options?.method === "PUT"
      ? new Response(
          JSON.stringify({ error: { code: "REVISION_CONFLICT", message: "内容已在其他页面修改" } }),
          { status: 409 },
        )
      : new Response(
          JSON.stringify({
            document_id: "doc",
            revision: 2,
            entry: { kind: "manual", title: "规范", content: "原文" },
          }),
        ),
  );
  vi.stubGlobal("fetch", fetch);
  render(
    <EntryEditor
      baseId="base"
      kind="manual"
      documentId="doc"
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  await waitFor(() => expect(screen.getByLabelText("正文")).toHaveValue("原文"));
  fireEvent.change(screen.getByLabelText("正文"), { target: { value: "我的修改" } });
  fireEvent.click(screen.getByRole("button", { name: "保存并入库" }));
  await screen.findByText("内容已在其他页面修改");
  expect(screen.getByLabelText("正文")).toHaveValue("我的修改");
  expect(screen.getByRole("button", { name: "保存并入库" })).toBeDisabled();
  const save = fetch.mock.calls.find(([, options]) => options?.method === "PUT")!;
  expect(JSON.parse(save[1]!.body as string).revision).toBe(2);
  fireEvent.click(screen.getByRole("button", { name: "放弃当前修改并加载最新版本" }));
  await waitFor(() => expect(screen.getByLabelText("正文")).toHaveValue("原文"));
});
it("does not allow writing over an entry that failed to load", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ detail: "读取失败" }), { status: 503 })),
  );
  render(
    <EntryEditor
      baseId="base"
      kind="manual"
      documentId="doc"
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  await screen.findByText("读取失败");
  expect(screen.getByLabelText("正文")).toBeDisabled();
  expect(screen.getByRole("button", { name: "保存并入库" })).toBeDisabled();
});

it("saves multiple phrasings with one answer and ignores blank lines", async () => {
  const fetch = vi.fn(async () => new Response(JSON.stringify({ id: "new", status: "pending" })));
  vi.stubGlobal("fetch", fetch);
  const saved = vi.fn();
  render(<EntryEditor baseId="base" kind="faq" onClose={vi.fn()} onSaved={saved} />);
  fireEvent.change(screen.getByLabelText("问题"), { target: { value: "如何报销？" } });
  fireEvent.change(screen.getByLabelText("标准答案"), { target: { value: "每晚620元。" } });
  fireEvent.change(screen.getByLabelText("相似问法（选填）"), {
    target: { value: "  酒店报销标准？\n\n住宿费上限？\n" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存并入库" }));
  await waitFor(() => expect(saved).toHaveBeenCalled());
  const call = fetch.mock.calls[0] as unknown as [string, RequestInit];
  expect(JSON.parse(call[1].body as string)).toEqual({
    kind: "faq",
    question: "如何报销？",
    answer: "每晚620元。",
    alternative_questions: ["酒店报销标准？", "住宿费上限？"],
  });
});

it("preserves oversized phrasings for editing and prevents invalid requests", () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  render(<EntryEditor baseId="base" kind="faq" onClose={vi.fn()} onSaved={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("问题"), { target: { value: "问题" } });
  fireEvent.change(screen.getByLabelText("标准答案"), { target: { value: "答案" } });
  const aliases = screen.getByLabelText("相似问法（选填）");
  fireEvent.change(aliases, { target: { value: "a\nb\nc\nd\ne\nf" } });
  expect(screen.getByText("最多填写 5 条相似问法。")).toBeVisible();
  expect(screen.getByRole("button", { name: "保存并入库" })).toBeDisabled();
  fireEvent.change(aliases, { target: { value: "问".repeat(151) } });
  expect(aliases).toHaveValue("问".repeat(151));
  expect(screen.getByRole("button", { name: "保存并入库" })).toBeDisabled();
  expect(fetch).not.toHaveBeenCalled();
});
