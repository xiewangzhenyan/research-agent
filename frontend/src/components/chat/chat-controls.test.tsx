import type { ReactNode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/auth-store";
import type { User } from "@/types";
import { ChatControls } from "./chat-controls";

vi.mock("next-intl", () => ({ useLocale: () => "zh" }));
// Layout/focus behavior is covered in the browser; isolate control policy from
// Floating UI's measurement loop in jsdom.
vi.mock("@/components/ui", () => ({
  Popover: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  PopoverTrigger: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  PopoverContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
let client: QueryClient;
beforeEach(() => {
  client = new QueryClient();
  useAuthStore.getState().setUser({ id: "owner" } as User);
});
afterEach(() => {
  client.clear();
  vi.unstubAllGlobals();
});
function mount(ui: ReactNode) {
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}
const config = {
  default: "reasoning",
  models: [
    {
      id: "reasoning",
      temperature: false,
      thinking_efforts: ["low", "medium", "high"],
      defaults: { temperature: null, thinking_effort: null },
    },
    {
      id: "standard",
      temperature: true,
      thinking_efforts: [],
      defaults: { temperature: 0.7, thinking_effort: null },
    },
  ],
};
async function open(props = {}) {
  mount(
    <ChatControls
      onModelChange={vi.fn()}
      onTemperatureChange={vi.fn()}
      onThinkingEffortChange={vi.fn()}
      {...props}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "聊天模型与设置" }));
  await screen.findByRole("button", { name: "standard" });
}
it("uses server capabilities and clears overrides on model changes", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(config))),
  );
  const temp = vi.fn();
  const effort = vi.fn();
  await open({ onTemperatureChange: temp, onThinkingEffortChange: effort });
  fireEvent.click(screen.getByRole("button", { name: "回答设置" }));
  expect(screen.getByLabelText("回答随机性（温度）")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "高" }));
  expect(effort).toHaveBeenLastCalledWith("high");
  fireEvent.click(screen.getByRole("button", { name: "生成模型" }));
  fireEvent.click(screen.getByRole("button", { name: "standard" }));
  expect(effort).toHaveBeenLastCalledWith(null);
  fireEvent.click(screen.getByRole("button", { name: "回答设置" }));
  expect(screen.getByLabelText("回答随机性（温度）")).toBeEnabled();
  expect(screen.getByRole("button", { name: "高" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("回答随机性（温度）"), { target: { value: "0.25" } });
  expect(temp).toHaveBeenLastCalledWith(0.25);
  fireEvent.click(screen.getByRole("button", { name: "恢复服务器默认" }));
  expect(temp).toHaveBeenLastCalledWith(null);
  expect(screen.queryByText(/no-ops/)).toBeNull();
});
it("keeps controls unavailable on failure and permits a retry", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response("{}", { status: 503 }))
    .mockResolvedValueOnce(new Response("{}", { status: 503 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(config)));
  vi.stubGlobal("fetch", fetch);
  mount(<ChatControls />);
  fireEvent.click(screen.getByRole("button", { name: "聊天模型与设置" }));
  await screen.findByRole("alert");
  expect(screen.queryByRole("button", { name: "standard" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
  await screen.findByRole("button", { name: "standard" });
});

it("restores a controlled snapshot and updates advanced parameters atomically", async () => {
  const extended = {
    ...config,
    models: config.models.map((m) => ({
      ...m,
      top_p: m.id === "standard",
      output_token_limits: [256, 32000],
    })),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(extended))),
  );
  const change = vi.fn();
  await open({
    value: { model: "standard", top_p: 0.4, max_output_tokens: 2048 },
    onChange: change,
  });
  fireEvent.click(screen.getByRole("button", { name: "回答设置" }));
  fireEvent.click(screen.getByText("更多参数"));
  expect(screen.getByLabelText("输出长度上限（Token）")).toHaveValue("2048");
  expect(screen.getByLabelText(/Top P ·/)).toHaveValue("0.4");
  fireEvent.change(screen.getByLabelText("回答随机性（温度）"), { target: { value: "0.25" } });
  expect(change).toHaveBeenLastCalledWith({
    model: "standard",
    temperature: 0.25,
    top_p: null,
    max_output_tokens: 2048,
  });
});
