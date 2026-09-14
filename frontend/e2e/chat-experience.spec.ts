import { test, expect, type Page } from "@playwright/test";
import { mockWorkspace } from "./fixtures";
import { readFile } from "node:fs/promises";

const cid = "bbbbbbbb-2222-4222-8222-222222222222";
const formula = String.raw`\[\varepsilon(\omega)=\varepsilon_\infty-\frac{\omega_p^2}{\omega^2+i\gamma\omega}\]`;
const answer = `Drude 模型描述自由电子对金属介电响应的贡献。\n\n${formula}\n\n其中，等离子体频率决定响应的主要频率尺度，阻尼项描述能量耗散。`;

async function setup(page: Page) {
  const fixture = await mockWorkspace(page);
  await page.route("**/api/conversations**", (route) =>
    route.fulfill({
      json: new URL(route.request().url()).pathname.endsWith(cid)
        ? { id: cid, active_knowledge_base_ids: [], knowledge_strict: true }
        : {
            items: [
              {
                id: cid,
                title: "理解金属的光学响应",
                created_at: "2026-09-13T01:00:00Z",
                updated_at: "2026-09-13T01:00:00Z",
              },
            ],
            total: 1,
          },
    }),
  );
  await page.route("**/api/chat/**", (route) =>
    route.fulfill({
      json: {
        runs: [],
        before: null,
        messages: [
          { id: "question", role: "user", content: "请解释 Drude 模型的介电函数。" },
          {
            id: "answer",
            role: "assistant",
            content: answer,
            thinking: "结合自由电子运动方程整理公式。",
          },
        ].map((m, i) => ({
          ...m,
          conversation_id: cid,
          created_at: `2026-09-13T01:00:0${i}Z`,
          files: [],
          tool_calls: [],
        })),
      },
    }),
  );
  await page.goto(`/chat?id=${cid}`);
  await expect(page.locator(".katex-display")).toBeVisible();
  return fixture;
}

test("composer stays quiet, math renders, Markdown exports and tools stay compact", async ({
  page,
}, testInfo) => {
  await setup(page);
  await expect(page.getByText("工具权限", { exact: true })).toHaveCount(0);
  const input = page.getByRole("textbox", { name: "输入消息" });
  await input.click();
  await expect(input).toHaveCSS("outline-style", "none");
  await expect(input).toHaveCSS("box-shadow", "none");
  const reasoning = page.getByRole("button", { name: "思考摘要" });
  await expect(reasoning).toHaveAttribute("aria-expanded", "false");
  await reasoning.click();
  await expect(reasoning).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator(".chat-reasoning-content")).toHaveCSS("transition-duration", "0s");
  await reasoning.click();
  await page.getByRole("button", { name: "导出回答" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载 Markdown" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.md$/);
  expect(await readFile((await file.path())!, "utf8")).toBe(answer);
  await page.getByRole("button", { name: "添加文件与工具" }).click();
  await expect(page.getByRole("button", { name: "上传文件" })).toBeVisible();
  await expect(page.getByRole("switch", { name: "数据分析" })).toBeDisabled();
  await page.keyboard.press("Escape");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: testInfo.outputPath("chat-experience.png"), fullPage: true });
  await page.getByRole("button", { name: "聊天模型与设置" }).click();
  await page.getByRole("button", { name: "回答设置", exact: true }).click();
  if (testInfo.project.name.includes("mobile")) {
    await expect(page.getByRole("dialog", { name: "模型与回答设置" })).toBeVisible();
    const panel = await page.getByRole("dialog", { name: "模型与回答设置" }).boundingBox();
    expect(Math.abs(panel!.y + panel!.height - page.viewportSize()!.height)).toBeLessThan(2);
  }
  await page.screenshot({ path: testInfo.outputPath("chat-settings.png"), fullPage: true });
});

test("microphone permission is allowed and recording errors are actionable", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "mediaDevices", {
      value: { getUserMedia: () => Promise.reject(new DOMException("Denied", "NotAllowedError")) },
      configurable: true,
    });
  });
  await setup(page);
  const response = await page.request.get("/login");
  expect(response.headers()["permissions-policy"]).toContain("microphone=(self)");
  await page.getByRole("textbox", { name: "输入消息" }).fill("保留这段草稿");
  await page.getByRole("button", { name: "语音输入" }).click();
  await expect(page.locator(".chat-composer").getByRole("alert")).toContainText("麦克风未获授权");
  await expect(page.getByRole("textbox", { name: "输入消息" })).toHaveValue("保留这段草稿");
});
