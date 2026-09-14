import { test, expect, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { mockWorkspace } from "./fixtures";

const cid = "bbbbbbbb-2222-4222-8222-222222222222";
const mid = "cccccccc-3333-4333-8333-333333333333";
const aid = "dddddddd-4444-4444-8444-444444444444";
const rid = "eeeeeeee-5555-4555-8555-555555555555";
const fid = "aaaaaaaa-1111-4111-8111-111111111111";
const binary = Buffer.from([80, 75, 3, 4, 0, 255, 12, 13]);

async function setup(page: Page) {
  await mockWorkspace(page);
  let generation: Record<string, unknown> = {
    model: "test",
    temperature: 0.3,
    max_output_tokens: 2048,
  };
  const requests: Record<string, unknown>[] = [];
  const run = () => ({
    id: rid,
    conversation_id: cid,
    user_message_id: mid,
    assistant_message_id: aid,
    created_at: "2026-09-13T01:00:00Z",
    status: "completed",
    attempt: 1,
    event_seq: 3,
    error: null,
    pending_input: null,
    effective_config: {
      model: "test",
      temperature: 0.3,
      max_output_tokens: generation.max_output_tokens,
      policy_version: "test",
    },
    request: { routing: { route: "standard", reason: "直接回答" } },
    result: null,
  });
  await page.route("**/api/agent/generation-config", (route) =>
    route.fulfill({
      json: {
        default: "test",
        policy_version: "test",
        models: [
          {
            id: "test",
            temperature: true,
            top_p: true,
            output_token_limits: [256, 32000],
            thinking_efforts: ["low", "medium", "high"],
            status: "configured",
            defaults: {
              model: "test",
              temperature: 0.7,
              max_output_tokens: 8000,
              thinking_effort: null,
              policy_version: "test",
            },
          },
        ],
      },
    }),
  );
  await page.route("**/api/conversations**", (route) =>
    route.fulfill({
      json: new URL(route.request().url()).pathname.endsWith(cid)
        ? { id: cid, active_knowledge_base_ids: [], knowledge_strict: true }
        : {
            items: [
              {
                id: cid,
                title: "实验报告",
                created_at: "2026-09-13T01:00:00Z",
                updated_at: "2026-09-13T01:00:00Z",
              },
            ],
            total: 1,
          },
    }),
  );
  await page.route("**/api/chat/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/export"))
      return route.fulfill({
        body: binary,
        contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      });
    if (url.pathname.endsWith("/turns")) {
      const body = route.request().postDataJSON();
      requests.push(body);
      generation = body.generation;
      return route.fulfill({ status: 201, json: run() });
    }
    return route.fulfill({
      json: {
        generation,
        runs: [run()],
        before: null,
        messages: [
          { id: mid, role: "user", content: "请整理实验数据。", tool_calls: [] },
          {
            id: aid,
            role: "assistant",
            content: "实验报告已生成，可使用下方文件卡片下载。",
            tool_calls: [
              {
                id: "tool1",
                tool_call_id: "doc1",
                tool_name: "create_document",
                args: {},
                status: "completed",
                result: JSON.stringify({
                  artifacts: [
                    {
                      id: fid,
                      run_id: rid,
                      name: "实验报告.docx",
                      size: binary.length,
                      mime_type: "application/octet-stream",
                    },
                  ],
                }),
                started_at: "2026-09-13T01:00:00Z",
              },
            ],
          },
        ].map((m, i) => ({
          ...m,
          conversation_id: cid,
          created_at: `2026-09-13T01:00:0${i}Z`,
          files: [],
        })),
      },
    });
  });
  await page.route(`**/api/tasks/${rid}/artifacts/${fid}`, (route) =>
    route.fulfill({ body: binary, contentType: "application/octet-stream" }),
  );
  await page.goto(`/chat?id=${cid}`);
  await expect(
    page.getByText("实验报告已生成，可使用下方文件卡片下载。", { exact: true }),
  ).toBeVisible();
  return { requests };
}
async function settings(page: Page) {
  await page.getByRole("button", { name: "聊天模型与设置" }).click();
  await page.getByRole("button", { name: "回答设置", exact: true }).click();
  await page.getByText("更多参数", { exact: true }).click();
}

test("restores conversation parameters, preserves unsent edits on refresh and saves with next message", async ({
  page,
}) => {
  const server = await setup(page);
  await settings(page);
  await expect(page.getByLabel("回答随机性（温度）")).toHaveValue("0.3");
  const cap = page.getByLabel("输出长度上限（Token）");
  await expect(cap).toHaveValue("2048");
  await cap.selectOption("4096");
  // A background state refresh must not overwrite the user's unsent edit.
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await expect(cap).toHaveValue("4096");
  await page.keyboard.press("Escape");
  await page.getByRole("textbox", { name: "输入消息" }).fill("使用这个设置继续解释");
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect.poll(() => server.requests.length).toBe(1);
  expect(server.requests[0]?.generation).toMatchObject({
    temperature: 0.3,
    max_output_tokens: 4096,
  });
  await page.reload();
  await settings(page);
  await expect(page.getByLabel("输出长度上限（Token）")).toHaveValue("4096");
});

test("shows persisted files inline and exports binary answers without a new generation", async ({
  page,
}, testInfo) => {
  const server = await setup(page);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载 实验报告.docx" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("实验报告.docx");
  expect(await readFile((await file.path())!)).toEqual(binary);
  await page.getByRole("button", { name: "导出回答" }).click();
  const exported = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载 Word", exact: true }).click();
  expect(await readFile((await (await exported).path())!)).toEqual(binary);
  expect(server.requests).toHaveLength(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: testInfo.outputPath("chat-deliverables.png"), fullPage: true });
});
