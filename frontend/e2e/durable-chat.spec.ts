import { test, expect, type Page } from "@playwright/test";
import { mockWorkspace, user } from "./fixtures";

const cid = "bbbbbbbb-2222-4222-8222-222222222222";
const mid = "cccccccc-3333-4333-8333-333333333333";
const aid = "dddddddd-4444-4444-8444-444444444444";
const rid = "eeeeeeee-5555-4555-8555-555555555555";
const projectId = "ffffffff-6666-4666-8666-666666666666";
const config = { model: "test", temperature: null, thinking_effort: null, policy_version: "test" };

function chatServer() {
  let submitted = false,
    completed = false,
    waiting = false;
  const requests: Record<string, unknown>[] = [];
  const turn = () => ({
    id: rid,
    conversation_id: cid,
    user_message_id: mid,
    assistant_message_id: aid,
    created_at: "2026-09-13T01:00:00Z",
    status: completed ? "completed" : waiting ? "waiting_input" : "running",
    attempt: 1,
    event_seq: 3,
    error: null,
    pending_input: waiting
      ? {
          question_id: "format-question",
          calls: [
            {
              call_id: "format-call",
              questions: [{ question: "采用哪种格式？", options: ["Markdown", "纯文本"] }],
            },
          ],
        }
      : null,
    effective_config: config,
    request: { routing: { route: "standard", reason: "直接回答" } },
    result: completed ? null : { content: "正在保存的部分内容", partial: true },
  });
  const messages = () =>
    [
      { id: "old-user", role: "user", content: "之前的问题", created_at: "2026-09-12T00:00:00Z" },
      {
        id: "old-assistant",
        role: "assistant",
        content: "之前保存的回答",
        created_at: "2026-09-12T00:00:01Z",
      },
      ...(submitted
        ? [
            {
              id: mid,
              role: "user",
              content: "请继续完成整理",
              created_at: "2026-09-13T01:00:00Z",
            },
            {
              id: aid,
              role: "assistant",
              content: completed ? "关闭网页后完成的完整回答" : "",
              created_at: "2026-09-13T01:00:01Z",
            },
          ]
        : []),
    ].map((m) => ({
      ...m,
      conversation_id: cid,
      files: [],
      tool_calls: [],
      effective_config: config,
    }));
  return {
    requests,
    ask: () => {
      submitted = true;
      waiting = true;
    },
    finish: () => {
      completed = true;
    },
    async attach(page: Page) {
      await mockWorkspace(page);
      await page.route("**/api/chat/**", async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.endsWith("/turns")) {
          requests.push(route.request().postDataJSON());
          submitted = true;
          return route.fulfill({ status: 201, json: turn() });
        }
        return route.fulfill({
          json: {
            runs: submitted ? [turn()] : [],
            ...(url.searchParams.get("include_messages") === "false"
              ? {}
              : { messages: messages(), before: null }),
          },
        });
      });
      await page.route("**/api/conversations**", (route) =>
        route.fulfill({
          json: new URL(route.request().url()).pathname.endsWith(cid)
            ? { id: cid, active_knowledge_base_ids: [], knowledge_strict: true }
            : {
                items: [
                  {
                    id: cid,
                    title: "保留的会话",
                    created_at: "2026-09-12T00:00:00Z",
                    updated_at: "2026-09-13T00:00:00Z",
                  },
                ],
                total: 1,
              },
        }),
      );
    },
  };
}

test("close and reopen restores transcript and completed turn with automatic execution", async ({
  page,
  context,
}) => {
  const server = chatServer();
  await server.attach(page);
  await page.goto(`/chat?id=${cid}`);
  await expect(page.getByText("之前保存的回答", { exact: true })).toBeVisible();
  await page.getByPlaceholder("输入消息...").fill("请继续完成整理");
  await page.getByPlaceholder("输入消息...").press("Enter");
  await expect(page.getByText("正在保存的部分内容", { exact: true })).toBeVisible();
  expect(server.requests).toHaveLength(1);
  expect(server.requests[0]?.conversation_id).toBe(cid);
  expect(server.requests[0]).not.toHaveProperty("mode");
  await page.close();
  server.finish();
  const reopened = await context.newPage();
  await server.attach(reopened);
  await reopened.goto("/chat");
  await expect(reopened.getByText("关闭网页后完成的完整回答", { exact: true })).toBeVisible();
  await expect(reopened.getByText("之前保存的回答", { exact: true })).toBeVisible();
  expect(server.requests).toHaveLength(1);
  await expect(reopened.getByRole("link", { name: "后台任务", exact: true })).toHaveCount(0);
  expect(await reopened.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
    true,
  );
});

test("slow project list does not block default workspace; explicit new chat stays empty", async ({
  page,
}) => {
  await mockWorkspace(page);
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/projects", async (route) => {
    await gate;
    await route.fulfill({ json: [] }).catch(() => {});
  });
  await page.addInitScript(({ key, cid }) => localStorage.setItem(key, cid), {
    key: `research-agent:last-chat:${user.id}:default`,
    cid,
  });
  try {
    await page.goto("/chat?new=1");
    await expect(page.getByPlaceholder("输入消息...")).toBeVisible();
    await expect(page.getByText("正在加载项目…", { exact: true })).toHaveCount(0);
    expect(new URL(page.url()).searchParams.get("id")).toBeNull();
  } finally {
    release();
  }
});

test("named project validates independently and keeps request scope", async ({ page }) => {
  const fixture = await mockWorkspace(page);
  const conversationHeaders: (string | undefined)[] = [];
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/projects", async (route) => {
    await gate;
    await route.fulfill({ json: [] }).catch(() => {});
  });
  await page.route(`**/api/projects/${projectId}`, (route) =>
    route.fulfill({
      json: { id: projectId, name: "指定项目", description: "", knowledge_base_ids: [] },
    }),
  );
  await page.route("**/api/conversations**", (route) => {
    conversationHeaders.push(route.request().headers()["x-project-id"]);
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  try {
    await page.goto(`/chat?project=${projectId}&new=1`);
    await expect(page.getByPlaceholder("输入消息...")).toBeVisible();
    await expect(page.getByRole("button", { name: "切换项目" })).toContainText("指定项目");
    await expect.poll(() => conversationHeaders.length).toBeGreaterThan(0);
    expect(conversationHeaders.every((id) => id === projectId)).toBe(true);
    expect(fixture.calls.filter((r) => r.path === "/api/auth/me")).toHaveLength(1);
  } finally {
    release();
  }
});

test("first send acknowledges a conversation and retries reuse the submission key", async ({
  page,
}) => {
  const server = chatServer();
  await server.attach(page);
  let lost = true;
  await page.route("**/api/chat/turns", async (route) => {
    if (lost) {
      lost = false;
      server.requests.push(route.request().postDataJSON());
      return route.fulfill({ status: 502, json: { detail: "发送尚未确认" } });
    }
    return route.fallback();
  });
  await page.goto("/chat?new=1");
  await page.getByPlaceholder("输入消息...").fill("请继续完成整理");
  await page.getByPlaceholder("输入消息...").press("Enter");
  await page.getByRole("button", { name: "重试发送", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`id=${cid}`));
  await expect(page.getByText("正在保存的部分内容", { exact: true })).toBeVisible();
  expect(server.requests).toHaveLength(2);
  expect(server.requests[0]?.idempotency_key).toBe(server.requests[1]?.idempotency_key);
  await expect(page.getByText("等待服务器确认", { exact: true })).toHaveCount(0);
});

test("restored clarification resumes from the same conversation", async ({ page }) => {
  const server = chatServer();
  server.ask();
  await server.attach(page);
  let reply: unknown;
  await page.route(`**/api/tasks/${rid}/resume`, async (route) => {
    reply = route.request().postDataJSON();
    server.finish();
    return route.fulfill({ json: {} });
  });
  await page.goto(`/chat?id=${cid}`);
  await expect(page.getByText("采用哪种格式？", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Markdown/ }).click();
  await expect(page.getByText("关闭网页后完成的完整回答", { exact: true })).toBeVisible();
  expect(reply).toEqual({
    question_id: "format-question",
    answers: { "format-call": ["Markdown"] },
  });
});
