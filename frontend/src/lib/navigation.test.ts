import { describe, expect, it } from "vitest";

import en from "../../messages/en.json";
import pl from "../../messages/pl.json";
import zh from "../../messages/zh.json";

import { ALL_NAV_ITEMS, MOBILE_TAB_KEYS, NAV_GROUPS, activeNavKey, navItem } from "./navigation";

describe("navigation config", () => {
  it("never links to the retired /tasks workspace", () => {
    expect(ALL_NAV_ITEMS.filter((item) => item.href.startsWith("/tasks"))).toEqual([]);
  });

  it("has a label for every item and group in each locale", () => {
    const keys = [...ALL_NAV_ITEMS.map((i) => i.key), ...NAV_GROUPS.map((g) => g.labelKey)];
    for (const catalog of [zh, en, pl]) {
      const nav = catalog.nav as Record<string, string>;
      expect(keys.filter((key) => !nav[key])).toEqual([]);
    }
  });

  it("keeps the test-visible Chinese labels", () => {
    expect(zh.nav.memory).toBe("项目记忆");
    expect(zh.nav.models).toBe("模型与能力");
    expect(zh.nav.chat).toBe("对话");
    expect(zh.nav.workspaceNav).toBe("工作台导航");
  });

  it("resolves mobile tabs to real items", () => {
    expect(MOBILE_TAB_KEYS.map((key) => navItem(key).href)).toEqual(["/knowledge", "/chat", "/dashboard"]);
  });

  it.each([
    ["/chat", "chat"],
    ["/en/memory", "memory"],
    ["/pl/settings/profile", "settings"],
    ["/admin/users", "admin"],
    ["/knowledge", "knowledge"],
    ["/dashboard", "dashboard"],
    ["/", "dashboard"],
    ["/somewhere-else", "dashboard"],
  ])("maps %s to %s", (path, key) => {
    expect(activeNavKey(path)).toBe(key);
  });
});
