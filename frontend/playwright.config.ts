import { defineConfig, devices } from "@playwright/test";

// UI contracts use mock APIs. Real database/ownership workflows have a separate CI job.
// No real user credentials or production services are required.
const external = process.env.PLAYWRIGHT_BASE_URL;
const port = Number(process.env.PLAYWRIGHT_PORT || 39000);
if (!Number.isInteger(port) || port < 1024 || port > 65535) {
  throw new Error("PLAYWRIGHT_PORT must be an unprivileged TCP port");
}
const local = `http://localhost:${port}`;
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  timeout: 30000,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: external || local,
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
        command: `node ./node_modules/next/dist/bin/next ${process.env.CI ? "start" : "dev"} --hostname localhost --port ${port}`,
        env: {
          NEXT_DIST_DIR: process.env.CI ? ".next" : ".next-e2e",
          NEXT_TELEMETRY_DISABLED: "1",
          BACKEND_URL: "http://127.0.0.1:9",
          OTEL_SDK_DISABLED: "true",
          OTEL_EXPORTER_OTLP_ENDPOINT: "http://127.0.0.1:9",
          OTEL_EXPORTER_OTLP_HEADERS: "",
        },
        url: local + "/login",
        reuseExistingServer: false,
        timeout: 120000,
      },
});
