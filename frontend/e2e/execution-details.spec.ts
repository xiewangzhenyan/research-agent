import { test, expect, type Page } from "@playwright/test";
import { mockWorkspace, user } from "./fixtures";
import type { Execution } from "../src/lib/execution-details";

const cid = "bbbbbbbb-2222-4222-8222-222222222222";
const rid = "eeeeeeee-5555-4555-8555-555555555555";
const projectId = "ffffffff-6666-4666-8666-666666666666";

async function executionServer(page: Page, overrides: Partial<Execution> = {}) {
  await mockWorkspace(page);
  const run: Execution = {
    id: rid,
    conversation_id: cid,
    user_message_id: "cccccccc-3333-4333-8333-333333333333",
    assistant_message_id: "dddddddd-4444-4444-8444-444444444444",
    created_at: "2026-09-13T01:00:00Z",
    status: "running",
    attempt: 1,
    event_seq: 3,
    error: null,
    pending_input: null,
    effective_config: {
      model: "test",
      temperature: null,
      thinking_effort: null,
      policy_version: "test",
    },
    request: {
      prompt: "整理数据并导出表格",
      tools: ["run_python"],
      routing: { route: "knowledge_collaboration", reason: "综合整理资料" },
    },
    result: { content: "已保存的分析内容" },
    ...overrides,
  };
  const taskRequests: { path: string; method: string; project?: string; body: unknown }[] = [];
  await page.route("**/api/chat/**", (route) =>
    route.fulfill({
      json: {
        runs: [run],
        messages: [
          { id: run.user_message_id, role: "user", content: "整理数据并导出表格" },
          { id: run.assistant_message_id, role: "assistant", content: "已保存的分析内容" },
        ].map((message, index) => ({
          ...message,
          conversation_id: cid,
          created_at: `2026-09-13T01:00:0${index}Z`,
          files: [],
          tool_calls: [],
        })),
        before: null,
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
                title: "数据分析",
                created_at: run.created_at,
                updated_at: run.created_at,
              },
            ],
            total: 1,
          },
    }),
  );
  await page.route("**/api/tasks/**", (route) => {
    const request = route.request(),
      url = new URL(request.url());
    taskRequests.push({
      path: url.pathname,
      method: request.method(),
      project: request.headers()["x-project-id"],
      body: request.postDataJSON(),
    });
    if (url.pathname === `/api/tasks/${rid}`) return route.fulfill({ json: run });
    if (url.pathname.endsWith("/events"))
      return route.fulfill({
        json: [
          { seq: 1, kind: "role_started", data: { role: "planner", message: "分析资料结构" } },
          { seq: 2, kind: "role_completed", data: { role: "planner", message: "整理步骤已确定" } },
          {
            seq: 3,
            kind: "python_result",
            data: { code: "print(42)", state: "completed", stdout: "42", exit_code: 0 },
          },
        ]
          .filter((event) => event.seq > Number(url.searchParams.get("after")))
          .map((event) => ({ ...event, created_at: run.created_at })),
      });
    if (url.pathname.endsWith("/artifacts"))
      return route.fulfill({
        json: [{ id: "file-1", name: "分析.csv", size: 16, mime_type: "text/csv" }],
      });
    if (url.pathname.endsWith("/artifacts/file-1"))
      return route.fulfill({ body: "value\n42\n", contentType: "text/csv" });
    if (url.pathname.endsWith("/cancel")) {
      run.status = "cancelled";
      return route.fulfill({ json: run });
    }
    if (url.pathname.endsWith("/resume")) {
      run.status = "completed";
      run.pending_input = null;
      run.result = { content: "补充信息后已完成" };
      return route.fulfill({ json: run });
    }
    return route.fallback();
  });
  return { run, taskRequests };
}

test("details and generated files stay in chat; closing stops reads without cancelling execution", async ({
  page,
}) => {
  const server = await executionServer(page);
  await page.goto(`/chat?id=${cid}`);
  const opener = page.getByRole("button", { name: "执行详情与文件", exact: true });
  await expect(opener).toBeVisible();
  expect(server.taskRequests.filter((r) => r.path.startsWith(`/api/tasks/${rid}`))).toHaveLength(0);
  await opener.click();
  const dialog = page.getByRole("dialog", { name: "执行详情与文件" });
  await expect(dialog.getByText("分析.csv", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("region", { name: "协作进度" })).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/chat");
  await dialog.getByText("执行步骤", { exact: true }).click();
  await dialog.getByText("代码与输出", { exact: false }).click();
  await expect(dialog.getByText("print(42)", { exact: true })).toBeVisible();
  const download = page.waitForEvent("download");
  await dialog.getByRole("button", { name: "下载 分析.csv" }).click();
  expect((await download).suggestedFilename()).toBe("分析.csv");
  expect(
    await dialog.evaluate(
      (element) =>
        element.getBoundingClientRect().width <= innerWidth &&
        element.scrollWidth <= element.clientWidth,
    ),
  ).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();
  await expect(page.getByText("已保存的分析内容", { exact: true })).toBeVisible();
  const reads = server.taskRequests.length;
  // Cross a complete detail polling interval to detect leaked observers after close.
  await page.waitForTimeout(2300);
  expect(server.taskRequests).toHaveLength(reads);
  expect(server.taskRequests.filter((r) => r.method === "POST")).toHaveLength(0);
  expect(new URL(page.url()).searchParams.get("id")).toBe(cid);
  expect(new URL(page.url()).searchParams.has("run")).toBe(false);
});

test("old task links open their conversation and retain the authorized project scope", async ({
  page,
}) => {
  const server = await executionServer(page, { status: "completed" });
  await page.route(`**/api/projects/${projectId}`, (route) =>
    route.fulfill({
      json: { id: projectId, name: "指定项目", description: "", knowledge_base_ids: [] },
    }),
  );
  await page.addInitScript(({ key }) => localStorage.setItem(key, "unrelated-conversation"), {
    key: `research-agent:last-chat:${user.id}:${projectId}`,
  });
  await page.goto(`/tasks?id=${rid}&project=${projectId}`);
  await expect(page.getByRole("dialog").getByText("分析.csv", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/chat\\?.*id=${cid}`));
  expect(
    server.taskRequests
      .filter((r) => r.path.startsWith(`/api/tasks/${rid}`))
      .every((r) => r.project === projectId),
  ).toBe(true);
  await page.getByRole("button", { name: "关闭详情" }).click();
  await expect(page.getByText("已保存的分析内容", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "切换项目" })).toContainText("指定项目");
});

test("retired task index redirects to chat and preserves locale", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/tasks");
  await expect(page.getByPlaceholder("输入消息...")).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/chat");
  await expect(page.locator('a[href*="/tasks"]')).toHaveCount(0);
  await page.goto("/en/tasks");
  await expect(page).toHaveURL(/\/en\/chat/);
});

test("detached legacy results and original citations remain readable inside chat", async ({
  page,
}) => {
  await executionServer(page, {
    conversation_id: null,
    status: "completed",
    result: {
      content: "历史整理结果 [1]",
      citations: [{ index: 1, title: "原始数据说明", page: 2, content: "原文片段保留" }],
    },
  });
  await page.goto(`/tasks?id=${rid}`);
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("历史整理结果", { exact: false })).toBeVisible();
  await dialog.getByTitle("Source [1]", { exact: true }).click();
  await expect(dialog.getByText("原文片段保留", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "下载 分析.csv" })).toBeVisible();
  expect(new URL(page.url()).searchParams.get("id")).toBeNull();
});

test("legacy clarification resumes and explicit stop still cancels the selected execution", async ({
  page,
}) => {
  const server = await executionServer(page, {
    conversation_id: null,
    status: "waiting_input",
    pending_input: {
      question_id: "format",
      calls: [
        {
          call_id: "format-call",
          questions: [{ question: "输出格式？", options: ["CSV", "JSON"] }],
        },
      ],
    },
  });
  await page.goto(`/tasks?id=${rid}`);
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("textbox", { name: /输出格式/ }).fill("CSV");
  await dialog.getByRole("button", { name: "保存并继续" }).click();
  await expect(dialog.getByText("补充信息后已完成", { exact: true })).toBeVisible();
  expect(server.taskRequests.find((r) => r.path.endsWith("/resume"))?.body).toEqual({
    question_id: "format",
    answers: { "format-call": ["CSV"] },
  });
  server.run.status = "running";
  await page.reload();
  await page.getByRole("dialog").getByRole("button", { name: "停止此条" }).click();
  await expect(page.getByRole("dialog").getByRole("status")).toHaveText("已停止");
  expect(server.taskRequests.filter((r) => r.path.endsWith("/cancel"))).toHaveLength(1);
});

test("mismatched conversation or revoked permission hides details and stops detail polling", async ({
  page,
}) => {
  const server = await executionServer(page, { conversation_id: projectId });
  await page.goto(`/chat?id=${cid}&run=${rid}`);
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("alert")).toContainText("不属于当前会话");
  await expect(dialog.getByText("整理数据并导出表格", { exact: true })).toHaveCount(0);
  expect(
    server.taskRequests.filter((r) => r.path.endsWith("/events") || r.path.endsWith("/artifacts")),
  ).toHaveLength(0);
  await dialog.getByRole("button", { name: "关闭详情" }).click();
  server.run.conversation_id = cid;
  await page.getByRole("button", { name: "执行详情与文件", exact: true }).click();
  await expect(dialog.getByText("分析.csv", { exact: true })).toBeVisible();
  let deniedReads = 0;
  await page.route(`**/api/tasks/${rid}`, (route) => {
    deniedReads++;
    return route.fulfill({ status: 403, json: { detail: "forbidden" } });
  });
  await expect(dialog.getByRole("alert")).toContainText("无权访问");
  await expect(dialog.getByText("分析.csv", { exact: true })).toHaveCount(0);
  await page.waitForTimeout(2300);
  expect(deniedReads).toBe(1);
});

test("closing during a pending stop does not restart detail reads when the server acknowledges", async ({
  page,
}) => {
  const server = await executionServer(page);
  let requested = false;
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(`**/api/tasks/${rid}/cancel`, async (route) => {
    requested = true;
    await gate;
    await route.fallback();
  });
  try {
    await page.goto(`/chat?id=${cid}&run=${rid}`);
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("分析.csv", { exact: true })).toBeVisible();
    await dialog.getByRole("button", { name: "停止此条" }).click();
    await expect.poll(() => requested).toBe(true);
    await dialog.getByRole("button", { name: "关闭详情" }).click();
    await expect(dialog).toHaveCount(0);
    const reads = () => server.taskRequests.filter((r) => r.method === "GET").length;
    const previous = reads();
    const acknowledged = page.waitForResponse((response) =>
      response.url().endsWith(`/tasks/${rid}/cancel`),
    );
    release();
    await acknowledged;
    await page.waitForTimeout(2300);
    expect(reads()).toBe(previous);
    expect(server.taskRequests.filter((r) => r.path.endsWith("/cancel"))).toHaveLength(1);
    await expect(page.getByText("已停止，已生成内容保留", { exact: false })).toBeVisible();
  } finally {
    release();
  }
});
