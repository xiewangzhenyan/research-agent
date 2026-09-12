import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { ArtifactPanel } from "./artifact-panel";
vi.mock("@/stores", () => ({
  useAuthStore: (select: (s: unknown) => unknown) => select({ user: { id: "account-a" } }),
}));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("refreshes files on task completion even if the last active poll was empty", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(new Response("[]"))
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify([{ id: "artifact-a", name: "结果.csv", size: 20, mime_type: "text/csv" }]),
      ),
    );
  vi.stubGlobal("fetch", fetcher);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = (finished: boolean) => (
    <QueryClientProvider client={client}>
      <ArtifactPanel runId="run-a" finished={finished} />
    </QueryClientProvider>
  );
  const { rerender } = render(view(false));
  await screen.findByText("暂无文件。计算成功并生成产物后将在此显示。");
  rerender(view(true));
  await waitFor(() =>
    expect(screen.getByRole("link", { name: "下载 结果.csv" })).toHaveAttribute(
      "href",
      "/api/tasks/run-a/artifacts/artifact-a",
    ),
  );
});
