import { afterEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TaskCard } from "./work-task-panel";
import type { WorkTask } from "@/lib/chat-turns";

vi.mock("@/hooks/use-file-download", () => ({
  useFileDownload: () => ({ download: vi.fn(), busy: null }),
}));
const clients: QueryClient[] = [];
afterEach(() => {
  clients.forEach((client) => client.clear());
  clients.length = 0;
});
const task: WorkTask = {
  id: "task-a",
  title: "比较方案并生成报告",
  status: "active",
  revision: 1,
  source_valid: true,
  next_action: "本轮结果待检查",
  updated_at: "2026-09-14",
  requirements: [],
  artifacts: [],
  steps: [
    {
      id: "step-a",
      run_id: "run-a",
      conversation_id: "chat-a",
      revision: 1,
      status: "completed",
      phase: "本轮已返回结果，待检查",
      historical: false,
    },
  ],
};
function setup(initial = task) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(client);
  const send = vi.fn().mockReturnValue(true);
  const view = (value: WorkTask) => (
    <QueryClientProvider client={client}>
      <TaskCard task={value} onSend={send} disabled={false} />
    </QueryClientProvider>
  );
  const mounted = render(view(initial));
  return { send, rerender: (value: WorkTask) => mounted.rerender(view(value)) };
}
it("uses exact task identity for continuation without asserting overall completion", () => {
  const { send } = setup();
  expect(screen.getByText("进行中 · v1")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "继续" }));
  expect(send).toHaveBeenCalledWith("继续之前的任务", {
    task_id: "task-a",
    action: "continue",
    expected_revision: 1,
  });
});
it("pins an edit to its original version even if another window updates the task", () => {
  const { send, rerender } = setup();
  fireEvent.click(screen.getByRole("button", { name: "调整要求" }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "只比较两种方案" } });
  rerender({ ...task, revision: 2 });
  fireEvent.click(screen.getByRole("button", { name: "保存要求并继续" }));
  expect(send).toHaveBeenCalledWith("只比较两种方案", {
    task_id: "task-a",
    action: "revise",
    expected_revision: 1,
  });
});
it("lets a running task be paused or revised, but doesn't enqueue duplicate continuation", () => {
  const { send } = setup({ ...task, steps: [{ ...task.steps[0]!, status: "waiting_input" }] });
  expect(screen.getByRole("button", { name: "继续" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "调整要求" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "暂停" }));
  expect(send).toHaveBeenCalledWith("暂停当前任务", expect.objectContaining({ action: "pause" }));
});
it("requires a complete new goal when a source is invalid", () => {
  const { send } = setup({ ...task, source_valid: false });
  expect(screen.getByRole("button", { name: "继续" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "重新设定目标" }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "新的完整目标" } });
  fireEvent.click(screen.getByRole("button", { name: "保存要求并继续" }));
  expect(send).toHaveBeenCalledWith("新的完整目标", expect.objectContaining({ action: "replace" }));
});
