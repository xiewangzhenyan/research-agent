import { test, expect, type Page } from "@playwright/test";
import { mockWorkspace } from "./fixtures";

const cid = "bbbbbbbb-2222-4222-8222-222222222222";
const tid = "cccccccc-3333-4333-8333-333333333333";
const rid = "dddddddd-4444-4444-8444-444444444444";
const aid = "eeeeeeee-5555-4555-8555-555555555555";
const task = {
  id: tid,
  title: "比较不同方案并生成报告",
  status: "active",
  revision: 1,
  source_valid: true,
  updated_at: "2026-09-14T01:00:00Z",
  next_action: "本轮结果待检查，可补充要求继续",
  requirements: [{ revision: 1, valid: true, content: "预算不超过 73 元，保留原文引用" }],
  steps: [
    {
      id: "step",
      run_id: rid,
      conversation_id: cid,
      revision: 1,
      status: "completed",
      phase: "本轮已返回结果，待检查",
      historical: false,
    },
  ],
  artifacts: [],
};
async function setup(page: Page, waiting = false) {
  await mockWorkspace(page);
  const requests: Record<string, unknown>[] = [];
  const current = structuredClone(task);
  if (waiting) {
    current.steps[0]!.status = "waiting_input";
    current.steps[0]!.phase = "等待补充信息";
  }
  await page.route("**/api/conversations**", (route) =>
    route.fulfill({
      json: new URL(route.request().url()).pathname.endsWith(cid)
        ? { id: cid, active_knowledge_base_ids: [], knowledge_strict: true }
        : { items: [{ id: cid, title: "已有对话", created_at: "2026-09-14T01:00:00Z" }], total: 1 },
    }),
  );
  await page.route("**/api/chat/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/work-tasks")) return route.fulfill({ json: { items: [current] } });
    if (url.pathname.endsWith(`/work-tasks/${tid}`)) return route.fulfill({ json: current });
    if (url.pathname.endsWith("/turns")) {
      const body = route.request().postDataJSON();
      requests.push(body);
      current.revision += 1;
      current.status = body.work_task.action === "pause" ? "paused" : "active";
      current.steps[0]!.status = "cancelled";
      return route.fulfill({ status: 201, json: { id: rid, conversation_id: cid } });
    }
    return route.fulfill({
      json: {
        generation: {},
        before: null,
        runs:
          waiting && current.status === "active"
            ? [
                {
                  id: rid,
                  conversation_id: cid,
                  assistant_message_id: aid,
                  user_message_id: tid,
                  status: "waiting_input",
                  created_at: "2026-09-14T01:00:00Z",
                  event_seq: 3,
                  attempt: 1,
                  request: {},
                  effective_config: {},
                  error: null,
                  result: null,
                  pending_input: {
                    question_id: "q",
                    calls: [
                      {
                        call_id: "format",
                        questions: [{ question: "选择导出格式", options: ["Word", "PPT"] }],
                      },
                    ],
                  },
                },
              ]
            : [],
        messages: [
          {
            id: aid,
            conversation_id: cid,
            role: "assistant",
            content: "前一步的工作结果",
            created_at: "2026-09-14T01:00:00Z",
            files: [],
            tool_calls: [],
          },
        ],
      },
    });
  });
  return requests;
}

test("task history and requirement editing stay within the chat on desktop and mobile", async ({
  page,
}, testInfo) => {
  const requests = await setup(page);
  await page.goto(`/chat?id=${cid}`);
  await page.getByRole("button", { name: "工作任务 · 1" }).click();
  await expect(page.getByRole("heading", { name: task.title })).toBeVisible();
  await page.getByRole("button", { name: "要求与执行记录" }).click();
  await expect(page.getByText("预算不超过 73 元，保留原文引用")).toBeVisible();
  await page.getByRole("button", { name: "调整要求", exact: true }).click();
  await page
    .getByRole("textbox", { name: "追加或修改要求（保留其他原有要求）" })
    .fill("只比较两种方案，改为 Markdown");
  expect(
    await page
      .getByRole("textbox", { name: "追加或修改要求（保留其他原有要求）" })
      .evaluate((el) => getComputedStyle(el).outlineStyle),
  ).toBe("none");
  await page.screenshot({ path: testInfo.outputPath("work-task-card.png"), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button", { name: "保存要求并继续" }).click();
  await expect.poll(() => requests.length).toBe(1);
  expect(requests[0]?.work_task).toEqual({ task_id: tid, expected_revision: 1, action: "revise" });
  expect(requests[0]?.message).toBe("只比较两种方案，改为 Markdown");
  expect(requests[0]).not.toHaveProperty("mode");
  await expect(
    page.getByRole("textbox", { name: "追加或修改要求（保留其他原有要求）" }),
  ).toHaveCount(0);
});

test("task controls remain usable while a run waits for human input", async ({ page }) => {
  const requests = await setup(page, true);
  await page.goto(`/chat?id=${cid}`);
  await expect(page.getByText("选择导出格式")).toBeVisible();
  await page.getByRole("button", { name: "工作任务 · 1" }).click();
  await page.getByRole("button", { name: "暂停", exact: true }).click();
  await expect.poll(() => requests.length).toBe(1);
  expect(requests[0]?.work_task).toEqual({ task_id: tid, expected_revision: 1, action: "pause" });
  expect(requests[0]).not.toHaveProperty("generation");
  expect(requests[0]).not.toHaveProperty("knowledge_base_ids");
  await expect(page.getByText("已暂停 · v2")).toBeVisible();
});

test("new conversations can explicitly continue an existing project task", async ({ page }) => {
  const requests = await setup(page);
  await page.goto("/chat?new=1");
  await page.getByRole("button", { name: "工作任务 · 1" }).click();
  await page.getByRole("button", { name: "继续", exact: true }).click();
  await expect.poll(() => requests.length).toBe(1);
  expect(requests[0]?.conversation_id).toBeNull();
  expect(requests[0]?.work_task).toEqual({
    task_id: tid,
    expected_revision: 1,
    action: "continue",
  });
});
