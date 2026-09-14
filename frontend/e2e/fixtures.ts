import type { Page } from "@playwright/test";

export const user = {
  id: "aaaaaaaa-1111-4111-8111-111111111111",
  email: "review@example.invalid",
  full_name: "测试用户",
  is_active: true,
  role: "user",
};
export async function mockWorkspace(page: Page, authenticated = true) {
  await page.addInitScript(() => localStorage.setItem("cookie.notice.read", "1"));
  const memory = {
    enabled: false,
    auto_extract: false,
    semantic_recall: true,
    extraction_model: "test",
    revision: 0,
    items: [] as Record<string, unknown>[],
    proposals: [],
    jobs: [],
    daily_jobs: 0,
    daily_limit: 20,
    limit: 100,
  };
  let signedIn = authenticated;
  const calls: { path: string; method: string; body: unknown }[] = [];
  await page.routeWebSocket("**/api/v1/ws/agent*", () => {});
  await page.route("**/api/**", async (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname,
      method = request.method();
    const body = request.postData() ? request.postDataJSON() : null;
    calls.push({ path, method, body });
    if (path === "/api/auth/me")
      return route.fulfill({
        status: signedIn ? 200 : 401,
        json: signedIn ? { ...user, access_token: "fixture" } : { detail: "unauthorized" },
      });
    if (path === "/api/auth/refresh")
      return route.fulfill({ status: 401, json: { detail: "unauthorized" } });
    if (path === "/api/auth/login") {
      if (body.email !== user.email || body.password !== "fixture-password")
        return route.fulfill({ status: 401, json: { detail: "Internal detail must not leak" } });
      signedIn = true;
      return route.fulfill({ json: { user, access_token: "fixture" } });
    }
    if (path === "/api/auth/logout") {
      signedIn = false;
      return route.fulfill({ json: {} });
    }
    if (path === "/api/projects") return route.fulfill({ json: [] });
    if (path === "/api/tasks") return route.fulfill({ json: [] });
    if (["/api/tools", "/api/tasks/tools"].includes(path))
      return route.fulfill({
        json: { items: [], sandbox: { status: "unavailable", file_execution: false } },
      });
    if (path === "/api/agent/models")
      return route.fulfill({ json: { models: ["test"], default: "test" } });
    if (["/api/agent/capabilities", "/api/agent/generation-config"].includes(path))
      return route.fulfill({
        json: {
          models: [
            {
              id: "test",
              status: "configured",
              thinking_efforts: [],
              temperature: false,
              defaults: {
                model: "test",
                temperature: null,
                thinking_effort: null,
                policy_version: "test",
              },
            },
          ],
          default: "test",
          policy_version: "test",
          embedding: {},
          rerank: {},
          capabilities: [],
        },
      });
    if (path === "/api/memory/settings") {
      Object.assign(memory, body, { auto_extract: body.enabled, revision: memory.revision + 1 });
      return route.fulfill({ json: memory });
    }
    if (path === "/api/memory") {
      if (method === "POST") {
        const item = {
          ...body,
          id: "bbbbbbbb-2222-4222-8222-222222222222",
          project_id: null,
          revision: 1,
          state: "active",
          index_status: "pending",
          created_at: new Date().toISOString(),
          updated_at: null,
        };
        memory.items.push(item);
        return route.fulfill({ status: 201, json: item });
      }
      return route.fulfill({ json: memory });
    }
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  return { calls, memory };
}
