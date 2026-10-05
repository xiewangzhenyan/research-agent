import { describe, expect, it } from "vitest";

import { groupByRecency } from "./conversation-groups";

const now = new Date(2026, 9, 5, 15, 0, 0);
const at = (days: number, hours = 0) =>
  new Date(2026, 9, 5 - days, 9 + hours, 0, 0).toISOString();

describe("groupByRecency", () => {
  it("buckets by local calendar day and keeps the incoming order", () => {
    const items = [
      { id: "a", updated_at: at(0, 4) },
      { id: "b", updated_at: at(0) },
      { id: "c", updated_at: at(1) },
      { id: "d", updated_at: at(4) },
      { id: "e", updated_at: at(20) },
      { id: "f", updated_at: at(90) },
    ];
    const groups = groupByRecency(items, now);
    expect(groups.map((g) => [g.key, g.items.map((i) => i.id)])).toEqual([
      ["today", ["a", "b"]],
      ["yesterday", ["c"]],
      ["week", ["d"]],
      ["month", ["e"]],
      ["earlier", ["f"]],
    ]);
  });

  it("omits empty groups and falls back to created_at", () => {
    const groups = groupByRecency([{ id: "x", updated_at: null, created_at: at(1) }], now);
    expect(groups).toEqual([{ key: "yesterday", items: [{ id: "x", updated_at: null, created_at: at(1) }] }]);
  });

  it("puts undated or unparsable items last", () => {
    const groups = groupByRecency([{ id: "y" }, { id: "z", updated_at: "not a date" }], now);
    expect(groups).toHaveLength(1);
    expect(groups[0]?.key).toBe("earlier");
  });
});
