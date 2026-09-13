import { act, cleanup, render, renderHook, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type { User } from "@/types";
import { useAuthStore } from "@/stores/auth-store";
import { Providers } from "@/app/providers";
import {
  GENERATION_CONFIG_STALE_TIME,
  GenerationConfigWarmup,
  useGenerationConfig,
} from "./use-generation-config";

vi.mock("@/components/theme", () => ({
  ThemeProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("@/components/ui", () => ({
  TooltipProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("sonner", () => ({ Toaster: () => null }));

let client: QueryClient;
const config = { default: "first", models: [], policy_version: "v1" };
const response = (value = config) => new Response(JSON.stringify(value));
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
function deferred() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
beforeEach(() => {
  client = new QueryClient();
  useAuthStore.getState().setUser({ id: "account-a" } as User);
});
afterEach(() => {
  cleanup();
  client.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("shares an in-flight request across navigation and reuses fresh data", async () => {
  const pending = deferred();
  const fetcher = vi.fn().mockReturnValue(pending.promise);
  vi.stubGlobal("fetch", fetcher);
  const warmup = render(<GenerationConfigWarmup />, { wrapper });
  const chat = renderHook(() => useGenerationConfig(), { wrapper });
  chat.unmount();
  const task = renderHook(() => useGenerationConfig(), { wrapper });
  expect(fetcher).toHaveBeenCalledOnce();
  expect(fetcher.mock.calls[0]![1].signal.aborted).toBe(false);
  pending.resolve(response());
  await waitFor(() => expect(task.result.current.data?.default).toBe("first"));
  task.unmount();
  const memory = renderHook(() => useGenerationConfig(), { wrapper });
  expect(memory.result.current.data?.default).toBe("first");
  expect(memory.result.current.isPending).toBe(false);
  expect(fetcher).toHaveBeenCalledOnce();
  warmup.unmount();
});

it("keeps cached choices visible during stale revalidation and deduplicates manual refresh", async () => {
  const fetcher = vi.fn().mockImplementation(async () => response());
  vi.stubGlobal("fetch", fetcher);
  const first = renderHook(() => useGenerationConfig(), { wrapper });
  await waitFor(() => expect(first.result.current.data).toEqual(config));
  first.unmount();
  const later = Date.now() + GENERATION_CONFIG_STALE_TIME + 1000;
  vi.spyOn(Date, "now").mockReturnValue(later);
  const pending = deferred();
  fetcher.mockImplementation(() => pending.promise);
  const next = renderHook(() => useGenerationConfig(), { wrapper });
  expect(next.result.current.data).toEqual(config);
  expect(next.result.current.isPending).toBe(false);
  expect(fetcher).toHaveBeenCalledTimes(2);
  let refresh!: Promise<unknown>;
  act(() => {
    refresh = Promise.all([next.result.current.refetch(), next.result.current.refetch()]);
  });
  expect(fetcher).toHaveBeenCalledTimes(2);
  await act(async () => {
    pending.resolve(response({ ...config, default: "updated", policy_version: "v2" }));
    await refresh;
  });
  await waitFor(() => expect(next.result.current.data?.default).toBe("updated"));
});

it("preserves choices after transient failure, but hides them after access is denied", async () => {
  const fetcher = vi.fn().mockImplementation(async () => response());
  vi.stubGlobal("fetch", fetcher);
  const view = renderHook(() => useGenerationConfig(), { wrapper });
  await waitFor(() => expect(view.result.current.data).toEqual(config));
  fetcher.mockImplementation(async () => new Response("{}", { status: 503 }));
  await act(async () => {
    await view.result.current.refetch();
  });
  await waitFor(() => expect(view.result.current.isError).toBe(true));
  expect(view.result.current.data).toEqual(config);
  fetcher.mockImplementation(async () => new Response("{}", { status: 403 }));
  const before = fetcher.mock.calls.length;
  await act(async () => {
    await view.result.current.refetch();
  });
  await waitFor(() => expect(view.result.current.data).toBeUndefined());
  expect(fetcher.mock.calls.length - before).toBe(1);
});

it("does not fetch without an account or when disabled", () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  renderHook(() => useGenerationConfig(false), { wrapper });
  act(() => useAuthStore.getState().setUser(null));
  const view = renderHook(() => useGenerationConfig(), { wrapper });
  expect(view.result.current.data).toBeUndefined();
  expect(fetcher).not.toHaveBeenCalled();
});

it("clears the old account cache and cancels pending work on logout", async () => {
  const clients: QueryClient[] = [];
  function Consumer() {
    const current = useQueryClient();
    if (!clients.includes(current)) clients.push(current);
    const query = useGenerationConfig();
    return <p>{query.data?.default ?? "loading"}</p>;
  }
  const fetcher = vi.fn().mockImplementation(async () => response());
  vi.stubGlobal("fetch", fetcher);
  render(
    <Providers>
      <Consumer />
    </Providers>,
  );
  await screen.findByText("first");
  const old = clients[0]!;
  const pending = deferred();
  fetcher.mockImplementation(() => pending.promise);
  act(() => useAuthStore.getState().setUser({ id: "account-b" } as User));
  expect(screen.queryByText("first")).not.toBeInTheDocument();
  expect(old.getQueryCache().getAll()).toHaveLength(0);
  const signal = fetcher.mock.calls.at(-1)![1].signal as AbortSignal;
  act(() => useAuthStore.getState().logout());
  expect(signal.aborted).toBe(true);
  expect(clients[1]!.getQueryCache().getAll()).toHaveLength(0);
  await act(async () => {
    pending.resolve(response({ ...config, default: "account-b" }));
  });
  expect(screen.queryByText("account-b")).not.toBeInTheDocument();
});
