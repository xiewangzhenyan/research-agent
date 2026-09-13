import { test, expect } from "@playwright/test";
import { mockWorkspace } from "./fixtures";

test("home has a heading, main landmark and no horizontal overflow", async ({ page }) => {
  await mockWorkspace(page, false);
  await page.goto("/");
  await expect(page).toHaveTitle(/Research Agent/);
  await expect(page.getByRole("main")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
