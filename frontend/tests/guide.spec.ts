import { expect, test } from "@playwright/test";

test("system guide explains the product and links back to the workspace", async ({ page }) => {
  await page.goto("/#guide");

  await expect(page.getByRole("heading", { name: "少读一点， 知道更多。" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "一条信息的旅程" })).toBeVisible();
  await expect(page.getByText("Source", { exact: true })).toBeVisible();
  await expect(page.getByText("机器辅助，人来判断", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "打开编辑工作台" }).click();
  await expect(page.getByRole("heading", { name: "从原始材料开始" })).toBeVisible();
});

test("system guide remains within a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#guide");
  await expect(page.getByRole("heading", { name: "少读一点， 知道更多。" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
