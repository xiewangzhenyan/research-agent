import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { CodeExecutionPanel } from "./code-execution-panel";
afterEach(cleanup);
it("displays failure and memory limit even when stdout exists", () => {
  const { container } = render(
    <CodeExecutionPanel
      result={{
        state: "failed",
        stdout: "partial",
        stderr: "MemoryError",
        oom_killed: true,
        exit_code: 137,
        protocol: 2,
      }}
    />,
  );
  expect(screen.getByText("执行失败")).toBeInTheDocument();
  expect(screen.queryByText("执行完成")).not.toBeInTheDocument();
  expect(screen.getByText("执行因内存超限而终止")).toBeInTheDocument();
  expect(container.querySelector("details")).toHaveAttribute("open");
});
it("escapes code and exposes truncated output", () => {
  const { container } = render(
    <CodeExecutionPanel
      result={{ state: "output_limit", code: "<script>alert(1)</script>", truncated: true }}
    />,
  );
  expect(container.querySelector("script")).toBeNull();
  expect(screen.getByText("输出超过 32 KiB，已截断并停止执行")).toBeInTheDocument();
});
