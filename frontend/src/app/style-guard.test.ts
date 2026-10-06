import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Style guard (ratchet), after WeKnora's assets/theme/styleGuard.test.mjs.
 * Counts patterns that bypass the design tokens in globals.css. Counts may only
 * go down: a new occurrence fails the test; after a cleanup, lower the baseline.
 */
const SRC = join(process.cwd(), "src");

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return /\.(tsx|ts|css)$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

interface Rule {
  name: string;
  why: string;
  files: RegExp;
  pattern: RegExp;
  baseline: number;
  exempt?: string[];
}

const RULES: Rule[] = [
  {
    name: "hex-in-tsx",
    why: "Use theme tokens (bg-brand, text-role-plan, var(--color-*)) so light/dark both follow.",
    files: /\.tsx$/,
    pattern: /#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3}(?:[0-9a-fA-F]{2})?)?\b(?![-\w])/g,
    // Brand artwork and metadata need literal colours.
    exempt: [
      "components/brand/research-mark.tsx",
      "app/opengraph-image.tsx",
      "app/global-error.tsx",
      "app/layout.tsx",
    ],
    baseline: 10,
  },
  {
    name: "dark-only-text",
    why: "Pale palette text (e.g. text-amber-200) is unreadable on the light theme; use text-warning / text-destructive or pair it with dark:.",
    files: /\.tsx$/,
    pattern: /(?<![\w:-])text-(?:red|amber|green|emerald|yellow|orange|lime|sky|blue|rose|slate)-(?:100|200|300|400)\b/g,
    baseline: 0,
  },
  {
    name: "transition-all",
    why: "transition-all animates layout properties too; list the properties that change.",
    files: /\.(tsx|css)$/,
    pattern: /\btransition-all\b|transition:\s*all\b/g,
    baseline: 5,
  },
  {
    name: "important",
    why: "!important is reserved for the reduced-motion override; use @layer order instead.",
    files: /\.css$/,
    pattern: /!important/g,
    baseline: 6,
  },
  {
    name: "css-radius-literal",
    why: "Use var(--radius-xs|sm|md|lg|xl|2xl|3xl|pill) (1/2/2/3/4/5/6/999px).",
    files: /\.css$/,
    pattern: /border-radius:\s*\d+(?:\.\d+)?px/g,
    baseline: 0,
  },
  {
    name: "css-transition-literal",
    why: "Use var(--motion-instant|fast|base|slow|cinematic) (120/150/200/300/560ms).",
    files: /\.css$/,
    pattern: /transition(?:-duration)?:[^;{]*?(?<![\w.-])\d*\.?\d+m?s\b/g,
    baseline: 2,
  },
];

const files = sourceFiles(SRC).map((path) => ({
  rel: relative(SRC, path),
  text: readFileSync(path, "utf8"),
}));

describe("style guard", () => {
  for (const rule of RULES) {
    it(`${rule.name} does not grow (baseline ${rule.baseline})`, () => {
      const hits = files
        .filter((f) => rule.files.test(f.rel) && !rule.exempt?.includes(f.rel))
        .flatMap((f) => (f.text.match(rule.pattern) ?? []).map(() => f.rel));
      const summary = Object.entries(
        hits.reduce<Record<string, number>>((acc, rel) => ({ ...acc, [rel]: (acc[rel] ?? 0) + 1 }), {}),
      )
        .map(([rel, n]) => `${rel}: ${n}`)
        .join("\n");
      expect(hits.length, `${rule.why}\n${summary}`).toBeLessThanOrEqual(rule.baseline);
    });
  }
});
