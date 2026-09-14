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

test("manual memory editing preserves content and expiry", async ({ page }) => {
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

test("automatic memory has one enable switch and exposes source without a review queue", async ({
  page,
}) => {
  const fixture = await mockWorkspace(page);
  await page.goto("/memory");
  await page.getByRole("switch", { name: "开启聊天记忆" }).click();
  await expect(page.getByRole("switch", { name: "开启聊天记忆" })).toBeChecked();
  expect(fixture.memory.auto_extract).toBe(true);
  await expect(page.getByText("待确认建议", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "核对并确认" })).toHaveCount(0);
  fixture.memory.items.push({
    id: "bbbbbbbb-2222-4222-8222-222222222222",
    project_id: null,
    revision: 1,
    title: "回答语言",
    content: "回答优先使用中文，保留专业术语英文。",
    kind: "preference",
    origin: "automatic",
    source_quote: "之后请用中文回答，专业术语保留英文。",
    source_message_id: null,
    state: "active",
    index_status: "ready",
    pinned: false,
    expires_on: null,
    archived_at: null,
    created_at: new Date().toISOString(),
    updated_at: null,
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "回答语言", exact: true })).toBeVisible();
  await expect(page.getByText("自动整理", { exact: true })).toBeVisible();
  await page.getByText("查看原文", { exact: true }).click();
  await expect(
    page.getByText("之后请用中文回答，专业术语保留英文。", { exact: true }),
  ).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
