import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["**/*.{test,spec}.{ts,tsx}"],
    exclude: ["node_modules", ".next", "e2e"],
    coverage: {
      provider: "v8",
      reporter: ["text-summary", "json", "json-summary", "html"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "node_modules",
        ".next",
        "e2e",
        "**/*.d.ts",
        "**/*.config.*",
        "vitest.setup.ts",
        "**/*.{test,spec}.{ts,tsx}",
      ],
      // Measured source-only baseline; critical paths have stronger separate gates.
      // Raise these floors as coverage grows. Do not include tests in the numerator.
      thresholds: {
        statements: 13.5,
        lines: 13.5,
        branches: 60,
        functions: 28,
        "src/lib/{auth-cookies,evidence-highlight}.ts": {
          statements: 100,
          lines: 100,
          branches: 100,
          functions: 100,
        },
        "src/lib/project-scope.ts": {
          statements: 100,
          lines: 100,
          branches: 85,
          functions: 80,
        },
        "src/app/api/{memory,tasks}/**/route.ts": {
          statements: 95,
          lines: 95,
          branches: 70,
          functions: 100,
        },
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
