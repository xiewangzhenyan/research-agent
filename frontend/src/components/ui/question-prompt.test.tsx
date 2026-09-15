import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { QuestionPrompt } from "./question-prompt";

vi.mock("next-intl", () => ({ useLocale: () => "zh" }));

it("requires critical answers, explains the blocker, and allows cancelling the turn", () => {
  const complete = vi.fn(),
    cancel = vi.fn();
  render(
    <QuestionPrompt
      questions={[
        {
          question: "处理哪份数据？",
          reason: "数据源不同会改变结果",
          required: true,
          options: ["数据 A", "数据 B"],
        },
      ]}
      onComplete={complete}
      onCancel={cancel}
    />,
  );
  expect(screen.getByText("数据源不同会改变结果")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "采用默认值" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "跳过可选问题" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "取消本轮" }));
  expect(cancel).toHaveBeenCalledOnce();
  expect(complete).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: /数据 A/ }));
  expect(complete).toHaveBeenCalledWith([{ answer: "数据 A", skipped: false }]);
});

it("cannot dismiss a set containing unanswered required questions", () => {
  const complete = vi.fn();
  render(
    <QuestionPrompt
      questions={[
        { question: "篇幅？", options: ["短", "长"] },
        { question: "哪份数据？", required: true },
      ]}
      onComplete={complete}
    />,
  );
  expect(screen.queryByRole("button", { name: "跳过可选问题" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "采用默认值" }));
  expect(screen.getByText("哪份数据？")).toBeInTheDocument();
  expect(complete).not.toHaveBeenCalled();
});

it("retrying or correcting the last answer does not append duplicate answers", () => {
  const complete = vi.fn();
  render(
    <QuestionPrompt
      questions={[
        { question: "数据？", required: true },
        { question: "范围？", required: true },
      ]}
      onComplete={complete}
    />,
  );
  fireEvent.change(screen.getByRole("textbox", { name: "补充信息" }), {
    target: { value: "数据 A" },
  });
  fireEvent.click(screen.getByRole("button", { name: "下一题" }));
  fireEvent.change(screen.getByRole("textbox", { name: "补充信息" }), {
    target: { value: "旧范围" },
  });
  fireEvent.click(screen.getByRole("button", { name: "提交并继续" }));
  // A rejected API response leaves this card mounted with the same question ID.
  fireEvent.change(screen.getByRole("textbox", { name: "补充信息" }), {
    target: { value: "新范围" },
  });
  fireEvent.click(screen.getByRole("button", { name: "提交并继续" }));
  expect(complete).toHaveBeenLastCalledWith([
    { answer: "数据 A", skipped: false },
    { answer: "新范围", skipped: false },
  ]);
});

it("records explicit optional skips and disables all submission paths during a request", () => {
  const complete = vi.fn();
  const ui = render(
    <QuestionPrompt
      questions={[{ question: "语气？", options: ["简洁", "详细"] }]}
      onComplete={complete}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "采用默认值" }));
  expect(complete).toHaveBeenCalledWith([{ answer: "", skipped: true }]);
  complete.mockClear();
  ui.rerender(
    <QuestionPrompt
      disabled
      questions={[{ question: "语气？", options: ["简洁", "详细"] }]}
      onComplete={complete}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "采用默认值" }));
  expect(complete).not.toHaveBeenCalled();
});

it("preserves previous answers and unsubmitted drafts when navigating back", () => {
  const complete = vi.fn();
  render(
    <QuestionPrompt
      questions={[
        { question: "对象？", required: true },
        { question: "范围？", required: true },
      ]}
      onComplete={complete}
    />,
  );
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "对象 A" } });
  fireEvent.click(screen.getByRole("button", { name: "下一题" }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "尚未提交的范围" } });
  fireEvent.click(screen.getByRole("button", { name: "返回上一题修改" }));
  expect(screen.getByRole("textbox")).toHaveValue("对象 A");
  fireEvent.click(screen.getByRole("button", { name: "下一题" }));
  expect(screen.getByRole("textbox")).toHaveValue("尚未提交的范围");
  fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter", isComposing: true });
  expect(complete).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "提交并继续" }));
  expect(complete).toHaveBeenCalledWith([
    { answer: "对象 A", skipped: false },
    { answer: "尚未提交的范围", skipped: false },
  ]);
});

it("shows external call parameters as literal text and requires a concrete decision", () => {
  const complete = vi.fn();
  render(
    <QuestionPrompt
      questions={[
        {
          question: "允许调用外部服务吗？",
          details: '{"value":"<script>doNotRun()</script>"}',
          required: true,
          allowCustom: false,
          options: ["拒绝本次调用", "允许本次调用"],
        },
      ]}
      onComplete={complete}
    />,
  );
  expect(screen.getByLabelText("本次调用参数")).toHaveTextContent("<script>doNotRun()</script>");
  expect(document.querySelector("script")).toBeNull();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(complete).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: /拒绝本次调用/ }));
  expect(complete).toHaveBeenCalledWith([{ answer: "拒绝本次调用", skipped: false }]);
});
