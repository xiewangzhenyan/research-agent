import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { InputFiles } from "./input-files";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("prevents uploading until capability and permission are available", () => {
  render(<InputFiles files={[]} onChange={vi.fn()} onBusy={vi.fn()} enabled={false} />);
  expect(screen.getByLabelText("添加计算文件")).toBeDisabled();
});
it("rejects oversized input before network transfer", () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  render(<InputFiles files={[]} onChange={vi.fn()} onBusy={vi.fn()} enabled />);
  const file = new File([new Uint8Array(5 * 1024 ** 2 + 1)], "large.csv");
  fireEvent.change(screen.getByLabelText("添加计算文件"), { target: { files: [file] } });
  expect(screen.getByRole("alert")).toHaveTextContent("总大小不超过 5 MiB");
  expect(fetcher).not.toHaveBeenCalled();
});
