import { test, expect, type Page } from "@playwright/test";
import { mockWorkspace } from "./fixtures";
const id = "dddddddd-4444-4444-8444-444444444444";
const entry = "---\nname: evidence-review\ndescription: 证据整理\n---\n先确认范围，再检查证据。";
async function setup(page: Page, kind: "skill" | "mcp", stdioReady = false) {
  await mockWorkspace(page);
  // API fixture, while real persistence and authorization are covered with PostgreSQL.
  let asset:
    (Record<string, unknown> & { revision: number; config: Record<string, unknown> }) | null = null;
  let binding = { asset_ids: [] as string[], revision: "empty" };
  const calls: {
    path: string;
    method: string;
    body: {
      asset_ids?: string[];
      config?: { enabled_tools: string[]; auto_approved_tools: string[] };
      secrets?: Record<string, string>;
    };
  }[] = [];
  await page.route("**/api/capabilities/**", async (route) => {
    const path = new URL(route.request().url()).pathname,
      method = route.request().method();
    const body = route.request().postData() ? route.request().postDataJSON() : null;
    calls.push({ path, method, body });
    if (path.endsWith("/availability"))
      return route.fulfill({
        json: { credentials_ready: true, stdio_ready: stdioReady, agent_keys: ["assistant"] },
      });
    if (path.endsWith("/bindings")) {
      if (method === "PUT") binding = { ...body, revision: "next" };
      return route.fulfill({ json: binding });
    }
    if (path.endsWith("/versions"))
      return route.fulfill({
        json: asset?.published_version
          ? [
              {
                version: 1,
                created_at: "2026-09-15T00:00:00Z",
                manifest: { name: "evidence-review" },
              },
            ]
          : [],
      });
    if (path.endsWith("/skills") || path.endsWith("/mcp")) {
      if (method === "GET") return route.fulfill({ json: asset ? [asset] : [] });
      asset = {
        ...body,
        id,
        kind,
        project_id: null,
        has_credentials: !!body.secrets,
        revision: 1,
        published_version: null,
        can_edit: true,
        can_bind: true,
        catalog: {},
        updated_at: "2026-09-15T00:00:00Z",
        status: kind === "skill" ? "draft" : "untested",
        last_tested: null,
        status_message: "",
      };
      delete asset!.secrets;
      if (kind === "skill")
        asset!.config = { ...asset!.config, files: [{ path: "SKILL.md", size: 100, sha256: "x" }] };
    } else if (path.endsWith("/publish"))
      asset = {
        ...asset!,
        revision: asset!.revision + 1,
        published_version: 1,
        status: "published",
      };
    else if (path.endsWith("/test"))
      asset = {
        ...asset!,
        revision: asset!.revision + 1,
        status: "ready",
        last_tested: "2026-09-15T00:00:00Z",
        status_message: "连接成功，已刷新能力列表",
        catalog: {
          tools: [{ name: "lookup", description: "查询公开资料", inputSchema: { type: "object" } }],
          resources: [],
          prompts: [],
        },
      };
    else if (method === "PUT") {
      asset = {
        ...asset!,
        ...body,
        revision: asset!.revision + 1,
        has_credentials: body.secrets
          ? Object.keys(body.secrets).length > 0
          : asset!.has_credentials,
      };
      delete asset!.secrets;
    } else if (method === "DELETE") {
      asset = null;
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({ json: asset });
  });
  return calls;
}
test("skill creation, publishing, binding and deletion", async ({ page }, testInfo) => {
  const calls = await setup(page, "skill");
  await page.goto("/skills");
  await page.getByRole("button", { name: "创建技能", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("名称", { exact: true }).fill("证据整理");
  await dialog.getByLabel("技能 Markdown 内容").fill(entry);
  await dialog.getByRole("button", { name: "保存并发布" }).click();
  await expect(dialog.getByText("已发布，请在列表中分配给当前助手")).toBeVisible();
  await dialog.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByRole("switch", { name: "当前助手使用 证据整理" }).click();
  await expect(page.getByRole("switch", { name: "当前助手使用 证据整理" })).toBeChecked();
  await page.getByRole("button", { name: "编辑 证据整理" }).click();
  await expect(dialog.getByLabel("技能 Markdown 内容")).toHaveValue(entry);
  await dialog.getByRole("tab", { name: "发布版本" }).click();
  await expect(dialog.getByText("版本 1", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("skills-management.png"), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await dialog.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByRole("button", { name: "删除 证据整理" }).click();
  await dialog.getByRole("button", { name: "删除", exact: true }).click();
  await expect(page.getByRole("heading", { name: "让常用方法成为可复用的技能" })).toBeVisible();
  expect(
    calls.find((c) => c.path.endsWith("/bindings") && c.method === "PUT")?.body.asset_ids,
  ).toEqual([id]);
});
test("MCP discovery, tool selection and binding use confirmation by default", async ({
  page,
}, testInfo) => {
  const calls = await setup(page, "mcp");
  await page.goto("/mcp");
  await page.getByRole("button", { name: "添加 MCP", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("名称", { exact: true }).fill("文献连接");
  await dialog.getByLabel("服务地址").fill("https://tools.example/mcp");
  await dialog.getByRole("button", { name: "保存并测试" }).click();
  await dialog.getByRole("checkbox", { name: "lookup", exact: true }).check();
  await expect(
    dialog.getByRole("checkbox", { name: "允许自动调用，无需逐次确认" }),
  ).not.toBeChecked();
  await dialog.getByRole("button", { name: "保存配置" }).click();
  await expect(dialog.getByText("配置已保存", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("mcp-permissions.png"), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await dialog.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByRole("switch", { name: "当前助手使用 文献连接" }).click();
  await expect(page.getByRole("switch", { name: "当前助手使用 文献连接" })).toBeChecked();
  const save = calls.filter((c) => c.method === "PUT" && c.path.endsWith(id)).at(-1)!;
  expect(save.body.config!.enabled_tools).toEqual(["lookup"]);
  expect(save.body.config!.auto_approved_tools).toEqual([]);
  expect(save.body.secrets).toBeUndefined();
});
test("stdio is unavailable until isolated runtime is ready and secrets never echo", async ({
  page,
}) => {
  await setup(page, "mcp");
  await page.goto("/mcp");
  await page.getByRole("button", { name: "添加 MCP", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("连接方式").selectOption("stdio");
  await expect(dialog.getByText(/隔离 MCP 执行节点尚未接通/)).toBeVisible();
  await expect(dialog.getByRole("button", { name: "保存并测试" })).toBeDisabled();
  await dialog.getByLabel("名称", { exact: true }).fill("本地工具");
  await dialog.getByLabel("启动命令", { exact: true }).fill("python");
  await dialog.getByRole("checkbox", { name: "替换凭据（空列表表示清空）" }).check();
  await dialog.getByRole("button", { name: "添加一项" }).click();
  await dialog.getByLabel("凭据名称 1").fill("API_KEY");
  await dialog.getByLabel("凭据内容 1").fill("dummy-secret-only");
  await dialog.getByRole("button", { name: "保存配置" }).click();
  await expect(dialog.getByText("已加密保存 · 留空保留原凭据")).toBeVisible();
  await expect(dialog.locator("input[type=password]")).toHaveCount(0);
});

test("ready stdio explains runtime limits and permits discovery", async ({ page }) => {
  await setup(page, "mcp", true);
  await page.goto("/mcp");
  await page.getByRole("button", { name: "添加 MCP", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("连接方式").selectOption("stdio");
  await expect(dialog.getByText(/隔离节点已就绪/)).toBeVisible();
  await dialog.getByLabel("名称", { exact: true }).fill("Python 工具");
  await dialog.getByLabel("启动命令", { exact: true }).fill("python");
  await expect(dialog.getByRole("button", { name: "保存并测试" })).toBeEnabled();
  await dialog.getByRole("button", { name: "保存并测试" }).click();
  await expect(dialog.getByText("查询公开资料", { exact: true })).toBeVisible();
});
