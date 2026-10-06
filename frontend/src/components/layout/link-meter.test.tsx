import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { LinkMeter } from "./link-meter";

vi.mock("next-intl", () => ({ useLocale: () => "zh" }));

afterEach(() => {
  vi.unstubAllGlobals();
});

it("reports the measured round trip to the API", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("{}", { status: 200 })),
  );
  render(<LinkMeter />);
  await waitFor(() => expect(screen.getByText(/^API \d+ms$/)).toBeInTheDocument());
  expect(screen.getByLabelText(/到服务器的往返延迟 \d+ 毫秒/)).toHaveAttribute(
    "data-state",
    "good",
  );
});

it("shows an error state when the API is unreachable", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Promise.reject(new TypeError("offline"))),
  );
  render(<LinkMeter />);
  await waitFor(() => expect(screen.getByText("API ERR")).toBeInTheDocument());
  expect(screen.getByLabelText("服务暂时无法连接")).toHaveAttribute("data-state", "down");
});
