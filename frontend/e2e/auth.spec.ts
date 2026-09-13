import { test, expect } from "@playwright/test";
import { mockWorkspace, user } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockWorkspace(page, false);
});

test("Chinese login has labelled controls and native required-field validation", async ({
  page,
}) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "登录工作空间" })).toBeVisible();
  await page.getByRole("button", { name: "登录", exact: true }).click();
  expect(
    await page
      .getByLabel("邮箱", { exact: true })
      .evaluate((input: HTMLInputElement) => input.validity.valueMissing),
  ).toBe(true);
  await expect(page.getByRole("link", { name: "注册", exact: true })).toBeVisible();
});

test("login failures are localized and password visibility preserves input", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill("wrong@example.invalid");
  const password = page.getByLabel("密码", { exact: true });
  await password.fill("wrong-password");
  await page.getByRole("button", { name: "显示密码" }).click();
  await expect(password).toHaveAttribute("type", "text");
  await expect(password).toHaveValue("wrong-password");
  await page.getByRole("button", { name: "隐藏密码" }).click();
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator("form").getByRole("alert")).toContainText("邮箱或密码错误");
  await expect(page.locator("form").getByRole("alert")).not.toContainText("Internal detail");
});

test("successful login opens the chat workspace", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(user.email);
  await page.getByLabel("密码", { exact: true }).fill("fixture-password");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/chat/);
  await expect(page.getByPlaceholder("输入消息...")).toBeVisible();
});

test("registration rejects mismatched passwords before submitting", async ({ page }) => {
  await page.goto("/register");
  await expect(page.getByRole("heading", { name: "创建你的账号" })).toBeVisible();
  await page.getByLabel("邮箱", { exact: true }).fill(user.email);
  await page.getByLabel("密码", { exact: true }).fill("fixture-password");
  await page.getByLabel("确认密码").fill("different-password");
  await page.getByRole("button", { name: "注册", exact: true }).click();
  await expect(page.locator("form").getByRole("alert")).toContainText("两次输入的密码不一致");
});
