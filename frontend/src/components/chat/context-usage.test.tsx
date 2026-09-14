import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ContextUsage } from "./context-usage";

let projectId = "project-a";
let userId = "account-a";
vi.mock("next-intl", () => ({ useLocale: () => "zh" }));
vi.mock("@/components/projects/project-provider", () => ({
  useProject: () => ({ project: { id: projectId } }),
}));
vi.mock("@/stores", () => ({
  useAuthStore: (fn: (s: unknown) => unknown) => fn({ user: { id: userId } }),
}));
afterEach(() => {
  vi.unstubAllGlobals();
  projectId = "project-a";
  userId = "account-a";
});
const props = {
  conversationId: "conversation-a",
  answerId: "answer-a",
  usage: {
    recent_messages: 12,
    references: [{ message_id: "old-message", via: "excerpt" }],
    omitted: false,
  },
};

it("loads only on expansion, forwards project scope, and shows verbatim history", async () => {
  const fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      items: [
        {
          message_id: "old-message",
          state: "available",
          role: "user",
          content: "做饭不放花生",
          partial: true,
        },
      ],
    }),
  });
  vi.stubGlobal("fetch", fetch);
  render(<ContextUsage {...props} />);
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "已衔接 1 段历史" }));
  expect(await screen.findByText("做饭不放花生")).toBeInTheDocument();
  expect(fetch.mock.calls[0]![1].headers).toEqual({ "X-Project-ID": "project-a" });
  expect(screen.getByText("你 · 节选")).toBeInTheDocument();
});

it("discards a late result after changing project, account, or conversation", async () => {
  let finish!: (v: unknown) => void;
  const fetch = vi.fn(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  vi.stubGlobal("fetch", fetch);
  const view = render(<ContextUsage {...props} />);
  fireEvent.click(screen.getByRole("button"));
  const signal = (fetch.mock.calls[0] as unknown as [string, RequestInit])[1].signal;
  projectId = "project-b";
  userId = "account-b";
  view.rerender(<ContextUsage {...props} conversationId="conversation-b" />);
  expect(signal?.aborted).toBe(true);
  await act(async () => {
    finish({
      ok: true,
      json: async () => ({
        items: [{ content: "PRIVATE", message_id: "old-message", state: "available" }],
      }),
    });
  });
  expect(screen.queryByText("PRIVATE")).not.toBeInTheDocument();
  expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "false");
});

it("shows source invalidation and allows a failed request to retry", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce({ ok: false })
    .mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ message_id: "old-message", state: "changed" }] }),
    });
  vi.stubGlobal("fetch", fetch);
  render(<ContextUsage {...props} />);
  fireEvent.click(screen.getByRole("button"));
  expect(await screen.findByText("历史暂时无法读取，请收起后重试。")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button"));
  fireEvent.click(screen.getByRole("button"));
  expect(await screen.findByText("原消息已修改或删除。")).toBeInTheDocument();
});
