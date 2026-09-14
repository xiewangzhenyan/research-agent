import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ChatInput } from "./chat-input";

vi.mock("next-intl", () => ({
  useLocale: () => "zh",
  useTranslations: () => (key: string) => key,
}));
vi.mock("./chat-tools-menu", () => ({
  ChatToolsMenu: () => <button type="button">上传文件</button>,
}));

it("does not send while choosing Chinese input candidates, and preserves Shift+Enter", () => {
  const onSend = vi.fn();
  render(<ChatInput onSend={onSend} />);
  const input = screen.getByRole("textbox", { name: "输入消息" });
  fireEvent.compositionStart(input);
  fireEvent.change(input, { target: { value: "光学" } });
  fireEvent.keyDown(input, { key: "Enter", keyCode: 229 });
  expect(onSend).not.toHaveBeenCalled();
  fireEvent.compositionEnd(input);
  fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
  expect(onSend).not.toHaveBeenCalled();
  fireEvent.keyDown(input, { key: "Enter" });
  expect(onSend).toHaveBeenCalledWith("光学", undefined, undefined);
  expect(input).toHaveValue("");
});

it("preserves a rejected draft and does not steal focus when generation completes", () => {
  const onSend = vi.fn(() => false);
  const { rerender } = render(
    <>
      <button>阅读引用</button>
      <ChatInput onSend={onSend} isProcessing />
    </>,
  );
  const input = screen.getByRole("textbox");
  fireEvent.change(input, { target: { value: "保留草稿" } });
  fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
  expect(input).toHaveValue("保留草稿");
  const other = screen.getByRole("button", { name: "阅读引用" });
  other.focus();
  rerender(
    <>
      <button>阅读引用</button>
      <ChatInput onSend={onSend} isProcessing={false} />
    </>,
  );
  expect(other).toHaveFocus();
});
