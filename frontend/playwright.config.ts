import { defineConfig, devices } from "@playwright/test";

// UI contracts use mock APIs. Real database/ownership workflows have a separate CI job.
// No real user credentials or production services are required.
const external = process.env.PLAYWRIGHT_BASE_URL;
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  timeout: 30000,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: external || "http://127.0.0.1:38000",
    locale: "zh-CN",
    reducedMotion: "reduce",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? {
          launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH },
        }
      : {}),
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chromium", use: { ...devices["Pixel 5"] } },
  ],
  webServer: external
    ? undefined
    : {
        command: process.env.CI ? "bun run start" : "bun run dev",
        url: "http://127.0.0.1:38000/login",
        reuseExistingServer: !process.env.CI,
        timeout: 120000,
      },
});
