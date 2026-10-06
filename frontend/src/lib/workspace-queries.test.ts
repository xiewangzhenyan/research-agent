import { describe, expect, it } from "vitest";

import {
  capabilityAssetsQuery,
  capabilityAvailabilityQuery,
  capabilityBindingsQuery,
  capabilityScope,
  knowledgeBasesQuery,
  toolsQuery,
} from "./workspace-queries";

// The idle prefetcher only helps if it writes the exact cache entries the pages read.
describe("workspace query keys", () => {
  it("keeps the keys the pages have always used", () => {
    expect(knowledgeBasesQuery("u1").queryKey).toEqual(["knowledge-bases", "u1"]);
    expect(toolsQuery("u1").queryKey).toEqual(["tools", "u1"]);
  });

  it("scopes capability lists by user and project, defaulting the project", () => {
    const scope = capabilityScope("u1", undefined);
    expect(scope).toEqual(["capabilities", "u1", "default"]);
    expect(capabilityAssetsQuery(scope, "mcp").queryKey).toEqual([
      "capabilities",
      "u1",
      "default",
      "mcp",
    ]);
    expect(capabilityBindingsQuery(capabilityScope("u1", "p1")).queryKey).toEqual([
      "capabilities",
      "u1",
      "p1",
      "bindings",
    ]);
    expect(capabilityAvailabilityQuery(scope).queryKey.at(-1)).toBe("availability");
  });

  it("does not run before a user is known", () => {
    expect(knowledgeBasesQuery(undefined).enabled).toBe(false);
    expect(toolsQuery(undefined).enabled).toBe(false);
  });
});
