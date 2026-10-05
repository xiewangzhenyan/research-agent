import { describe, expect, it } from "vitest";

import type { ToolCall } from "@/types";

import { summarizeRetrieval, toolCallsOf } from "./run-summary";

const call = (id: string): ToolCall => ({ id, name: "search_knowledge_base", args: {}, status: "completed" });

describe("toolCallsOf", () => {
  it("prefers the ordered parts timeline", () => {
    const parts = [
      { id: "t", type: "text" as const, content: "hi" },
      { id: "a", type: "tool" as const, toolCall: call("a") },
      { id: "b", type: "tool" as const, toolCall: call("b") },
    ];
    expect(toolCallsOf({ parts, toolCalls: [call("legacy")] }).map((c) => c.id)).toEqual(["a", "b"]);
  });

  it("falls back to the legacy tool list", () => {
    expect(toolCallsOf({ toolCalls: [call("x")] }).map((c) => c.id)).toEqual(["x"]);
    expect(toolCallsOf({})).toEqual([]);
  });
});

describe("summarizeRetrieval", () => {
  it("counts passages and distinct documents", () => {
    expect(summarizeRetrieval([{ source: "a.pdf" }, { source: "b.pdf" }, { source: "a.pdf" }])).toEqual({
      passages: 3,
      documents: 2,
    });
  });

  it("returns null for an empty result", () => {
    expect(summarizeRetrieval([])).toBeNull();
  });
});
