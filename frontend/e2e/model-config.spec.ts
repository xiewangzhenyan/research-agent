import { test, expect, type Page } from "@playwright/test";
import { mockWorkspace } from "./fixtures";

async function navigate(page: Page, name: string) {
  const menu = page.getByRole("button", { name: "切换菜单" });
  if (await menu.isVisible()) await menu.click();
  await page
    .getByRole("navigation", { name: "工作台导航" })
    .getByRole("link", { name, exact: true })
    .click();
}

test("model selectors reuse cached config across chat, memory and settings", async ({ page }) => {
  const fixture = await mockWorkspace(page);
  fixture.memory.enabled = true;
  const generationCalls = () =>
    fixture.calls.filter((call) => call.path === "/api/agent/generation-config");
  const runtimeCalls = () =>
    fixture.calls.filter((call) => call.path === "/api/agent/capabilities");
  await page.goto("/chat");
  await expect(page.getByRole("button", { name: "聊天模型与设置" })).toContainText("test");
  // Development Strict Mode can abort an initial request during its mount check.
  // Navigation itself must make no additional generation-config requests.
  const initialRequests = generationCalls().length;
  expect(initialRequests).toBeGreaterThan(0);
  if (process.env.CI) expect(initialRequests).toBe(1);
  await navigate(page, "项目记忆");
  await expect(page.getByLabel("记忆提取模型")).toHaveValue("test");
  await navigate(page, "模型与能力");
  await expect(page.getByRole("heading", { name: "回答生成模型" })).toBeVisible();
  expect(generationCalls()).toHaveLength(initialRequests);
  expect(runtimeCalls()).toHaveLength(0);
  await page.getByRole("button", { name: "刷新状态", exact: true }).click();
  await expect.poll(() => generationCalls().length).toBe(initialRequests + 1);
  await page.getByRole("tab", { name: "知识模型", exact: true }).click();
  await expect.poll(() => runtimeCalls().length).toBe(1);
  await navigate(page, "对话");
  await expect(page.getByRole("button", { name: "聊天模型与设置" })).toContainText("test");
  expect(generationCalls()).toHaveLength(initialRequests + 1);
});
