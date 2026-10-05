import { describe, expect, it } from "vitest";

import en from "../messages/en.json";
import pl from "../messages/pl.json";
import zh from "../messages/zh.json";

/** Locale key audit (pattern from WeKnora's src/i18n/localeKeyAudit.test.ts). */
function keys(messages: Record<string, unknown>, prefix = ""): string[] {
  return Object.entries(messages).flatMap(([key, value]) =>
    value && typeof value === "object" && !Array.isArray(value)
      ? keys(value as Record<string, unknown>, `${prefix}${key}.`)
      : [`${prefix}${key}`],
  );
}

describe("message catalogs", () => {
  const reference = new Set(keys(zh));

  it.each([
    ["en", en],
    ["pl", pl],
  ])("%s has exactly the zh keys", (_locale, catalog) => {
    const other = new Set(keys(catalog as Record<string, unknown>));
    expect([...reference].filter((k) => !other.has(k)), "missing").toEqual([]);
    expect([...other].filter((k) => !reference.has(k)), "extra").toEqual([]);
  });

  it("has no empty strings", () => {
    for (const catalog of [zh, en, pl]) {
      const empty = keys(catalog).filter((k) => {
        const value = k.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown>)[part], catalog);
        return typeof value === "string" && value.trim() === "";
      });
      expect(empty).toEqual([]);
    }
  });
});
