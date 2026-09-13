import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryEditor, RememberMessage } from "./memory-editor";
import { MemoryUsageBadge } from "./memory-usage";
import { useAuthStore } from "@/stores";
import { activateProject } from "@/lib/project-scope";
import type { ChatMessage, User } from "@/types";
import type { MemoryItem } from "@/lib/memory";
import MemoryPage from "@/app/[locale]/(dashboard)/memory/page";

vi.mock("next-intl", async (original) => ({
  ...(await original<object>()),
  useLocale: () => "zh",
}));
vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
const message = { id, role: "assistant", content: "超表面的测量要求" } as ChatMessage;
const item = {
  id,
  title: "约束",
  content: "测量温度固定",
  kind: "constraint",
  pinned: false,
  revision: 3,
  source_message_id: null,
} as MemoryItem;
beforeEach(() => {
  useAuthStore.getState().setUser({ id: "owner" } as User);
  activateProject("owner", null);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
function mount(ui: React.ReactNode) {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      {ui}
    </QueryClientProvider>,
  );
}
it("requires confirmation and saves the source only after review", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(item)));
  vi.stubGlobal("fetch", fetcher);
  mount(<RememberMessage message={message} />);
  fireEvent.click(screen.getByRole("button", { name: "记住这条消息" }));
  expect(screen.getByLabelText("需要记住的内容")).toHaveValue(message.content);
  expect(fetcher).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("需要记住的内容"), {
    target: { value: "已确认的测量要求" },
  });
  fireEvent.click(screen.getByRole("button", { name: "确认保存" }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledOnce());
  expect(JSON.parse(fetcher.mock.calls[0]![1].body)).toMatchObject({
    content: "已确认的测量要求",
    source_message_id: id,
  });
});
it("never silently truncates a long message or enables saving over the limit", () => {
  mount(<MemoryEditor message={{ ...message, content: "字".repeat(1201) }} onClose={() => {}} />);
  expect(screen.getByLabelText("需要记住的内容")).toHaveValue("字".repeat(1201));
  expect(screen.getByRole("button", { name: "确认保存" })).toBeDisabled();
});
it("keeps edited input and reports revision conflicts", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(
      new Response(JSON.stringify({ error: { message: "内容已更新，请刷新" } }), { status: 409 }),
    );
  vi.stubGlobal("fetch", fetcher);
  const closed = vi.fn();
  mount(<MemoryEditor item={item} onClose={closed} />);
  fireEvent.change(screen.getByLabelText("需要记住的内容"), { target: { value: "新的限制条件" } });
  fireEvent.click(screen.getByRole("button", { name: "确认保存" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("内容已更新");
  expect(JSON.parse(fetcher.mock.calls[0]![1].body).revision).toBe(3);
  expect(screen.getByLabelText("需要记住的内容")).toHaveValue("新的限制条件");
  expect(closed).not.toHaveBeenCalled();
});
it("hides save on temporary messages and links only IDs and revisions in usage", () => {
  const { container } = mount(<RememberMessage message={{ ...message, isTemporaryId: true }} />);
  expect(container).toBeEmptyDOMElement();
  mount(
    <MemoryUsageBadge
      usage={{ status: "used", items: [{ id, revision: 3 }], omitted: 1, estimated_tokens: 50 }}
    />,
  );
  expect(screen.getByRole("link")).toHaveAttribute(
    "href",
    `/memory?used=${encodeURIComponent(id + ":3")}`,
  );
});
it("renders disabled consent by default and saves the settings revision", async () => {
  let enabled = false;
  const fetcher = vi.fn(async (_url: string, init: RequestInit) => {
    if (init.method === "PUT") {
      enabled = true;
      return new Response(JSON.stringify({ enabled, revision: 1 }));
    }
    return new Response(
      JSON.stringify({ enabled, revision: enabled ? 1 : 0, items: [], limit: 100 }),
    );
  });
  vi.stubGlobal("fetch", fetcher);
  mount(<MemoryPage />);
  await screen.findByText("从一条值得保留的信息开始");
  expect(screen.getByRole("switch")).not.toBeChecked();
  fireEvent.click(screen.getByRole("switch"));
  await waitFor(() => expect(screen.getByRole("switch")).toBeChecked());
  const mutation = fetcher.mock.calls.find((c) => c[1].method === "PUT")!;
  expect(JSON.parse(mutation[1].body as string)).toEqual({ enabled: true, revision: 0 });
});
