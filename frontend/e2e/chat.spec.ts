import { test, expect } from "@playwright/test";
import { mockWorkspace } from "./fixtures";

test("chat accepts a draft without losing content on mobile", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/chat");
  const input = page.getByPlaceholder("输入消息...");
  await expect(input).toBeVisible();
  await input.fill("请分析这份文献的测量条件，保留数值和限制。");
  await expect(input).toHaveValue("请分析这份文献的测量条件，保留数值和限制。");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("project memory requires explicit confirmation and keeps expiry", async ({ page }) => {
  const fixture = await mockWorkspace(page);
  await page.goto("/memory");
  await expect(page.getByRole("heading", { name: "项目记忆", exact: true })).toBeVisible();
  await expect(page.getByRole("switch", { name: "开启聊天记忆" })).not.toBeChecked();
  await page.getByRole("button", { name: "添加记忆", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("标题", { exact: true }).fill("测量要求");
  await dialog.getByLabel("需要记住的内容").fill("测量温度为 25°C，不允许覆盖原始数据。");
  await dialog.getByLabel("有效至（可选）").fill("2099-01-31");
  expect(fixture.memory.items).toHaveLength(0);
  await dialog.getByRole("button", { name: "确认保存", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("heading", { name: "测量要求", exact: true })).toBeVisible();
  expect(fixture.memory.items[0]).toMatchObject({
    expires_on: "2099-01-31",
    content: "测量温度为 25°C，不允许覆盖原始数据。",
  });
  expect(fixture.memory.enabled).toBe(false);
});
