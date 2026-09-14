import { expect, test } from "@playwright/test";
import { mockWorkspace } from "./fixtures";

const cid = "bbbbbbbb-2222-4222-8222-222222222222";
const aid = "dddddddd-4444-4444-8444-444444444444";

test("earlier history is disclosed in place without stretching mobile chat", async ({
  page,
}, testInfo) => {
  await mockWorkspace(page);
  await page.route("**/api/conversations**", (route) =>
    route.fulfill({
      json: new URL(route.request().url()).pathname.endsWith(cid)
        ? { id: cid, active_knowledge_base_ids: [], knowledge_strict: false }
        : {
            items: [{ id: cid, title: "跨话题讨论", created_at: "2026-09-14T01:00:00Z" }],
            total: 1,
          },
    }),
  );
  let historyRequests = 0;
  await page.route("**/api/chat/**", (route) => {
    if (route.request().url().endsWith("/context")) {
      historyRequests += 1;
      return route.fulfill({
        json: {
          items: [
            {
              message_id: "old",
              state: "available",
              role: "user",
              content: "做饭不要放花生，过敏；预算三十元。",
              partial: false,
            },
          ],
        },
      });
    }
    return route.fulfill({
      json: {
        runs: [],
        before: null,
        messages: [
          { id: "question", role: "user", content: "回到做饭，刚才有哪些限制？" },
          {
            id: aid,
            role: "assistant",
            content: "你之前提到花生过敏，预算为三十元。",
            effective_config: {
              model: "test",
              policy_version: "v1",
              context: {
                recent_messages: 12,
                references: [{ message_id: "old", via: "summary" }],
                omitted: false,
              },
            },
          },
        ].map((message, i) => ({
          ...message,
          conversation_id: cid,
          created_at: `2026-09-14T01:00:0${i}Z`,
          files: [],
          tool_calls: [],
        })),
      },
    });
  });
  await page.goto(`/chat?id=${cid}`);
  const disclosure = page.getByRole("button", { name: "已衔接 1 段历史" });
  await expect(disclosure).toBeVisible();
  expect(historyRequests).toBe(0);
  await disclosure.click();
  await expect(page.getByText("做饭不要放花生，过敏；预算三十元。", { exact: true })).toBeVisible();
  expect(historyRequests).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: testInfo.outputPath("conversation-context.png"), fullPage: true });
  await disclosure.click();
  await expect(
    page.getByText("做饭不要放花生，过敏；预算三十元。", { exact: true }),
  ).not.toBeVisible();
});
