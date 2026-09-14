import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useFileDownload } from "./use-file-download";
import { useAuthStore } from "@/stores";
import { activateProject } from "@/lib/project-scope";
import type { User } from "@/types";
vi.mock("next-intl", () => ({ useLocale: () => "zh" }));
vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));
const createUrl = vi.fn(() => "blob:test");
beforeEach(() => {
  useAuthStore.getState().setUser({ id: "owner" } as User);
  activateProject("owner", null);
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createUrl });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  createUrl.mockClear();
});
it("ignores a download that arrives after account switching", async () => {
  let resolve!: (r: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise<Response>((r) => {
          resolve = r;
        }),
    ),
  );
  const { result } = renderHook(() => useFileDownload("message"));
  let pending!: Promise<void>;
  act(() => {
    pending = result.current.download("/api/tasks/run/artifacts/id", "report.docx");
  });
  act(() => {
    useAuthStore.getState().setUser({ id: "other" } as User);
  });
  await act(async () => {
    resolve(new Response("private content"));
    await pending;
  });
  expect(createUrl).not.toHaveBeenCalled();
});
it("checks the active project again before creating a browser download", async () => {
  let resolve!: (r: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise<Response>((r) => {
          resolve = r;
        }),
    ),
  );
  const { result } = renderHook(() => useFileDownload("message"));
  let pending!: Promise<void>;
  act(() => {
    pending = result.current.download("/api/tasks/run/artifacts/id", "report.docx");
  });
  activateProject("owner", {
    id: "different",
    name: "other",
    description: "",
    knowledge_base_ids: [],
  });
  await act(async () => {
    resolve(new Response("old project content"));
    await pending;
  });
  expect(createUrl).not.toHaveBeenCalled();
});
it("downloads successful content only on demand", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response("document bytes"));
  vi.stubGlobal("fetch", fetch);
  const { result } = renderHook(() => useFileDownload("message"));
  expect(fetch).not.toHaveBeenCalled();
  await act(async () => {
    await result.current.download("/api/chat/messages/id/export", "report.docx", {
      method: "POST",
    });
  });
  expect(createUrl).toHaveBeenCalledTimes(1);
  expect(result.current.busy).toBeNull();
});
