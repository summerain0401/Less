import { expect, test } from "@playwright/test";

test("real local backend exposes source health and original snapshots", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "从原始材料开始" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "来源管理" }).click();
  await expect(
    page.getByRole("heading", { name: "Source Registry" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "OpenAI Codex Releases" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "运行记录" }).click();
  await expect(
    page.getByRole("heading", { name: "采集记录", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "原始材料" }).click();
  await expect(page.locator(".item-row").first()).toBeVisible();
  await page.locator(".item-row").first().click();
  await expect(
    page.getByText("原文 · 保存版本", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "保存快照" })).toBeVisible();
  expect(await page.locator(".paragraph").count()).toBeGreaterThan(0);
});

test("review requires a name and note, submits the exact run, and survives rerun", async ({
  page,
}) => {
  // Clearly synthetic browser fixture; never writes an approval into the real database.
  const version = {
    id: "fixture-v1",
    item_id: "fixture-item",
    title: "Browser test fixture",
    text: "Original statement.",
    author: null,
    published_at: null,
    captured_at: "2026-09-20T00:00:00Z",
    acquisition: "test-fixture",
    content_hash: "fixture",
    paragraphs: [
      { id: "p0001", text: "Original statement.", start: 0, end: 19 },
    ],
    limitations: [],
  };
  const run = {
    id: "fixture-run",
    version_id: version.id,
    status: "succeeded",
    attempts: 1,
    error: null,
    created_at: version.captured_at,
    prompt_version: "test-v1",
    model: "test-double",
    metadata: { cost: null },
    raw_output: null,
    output: {
      summary: "测试摘要",
      language: "en",
      claims: [
        {
          text: "测试陈述",
          kind: "fact_candidate",
          quote: "Original statement.",
          paragraph_ids: ["p0001"],
        },
      ],
      entities: [],
      topics: [],
      uncertainties: [],
    },
  };
  const reviews: unknown[] = [];
  const runs: unknown[] = [run];
  await page.route("**/api/items", (route) =>
    route.fulfill({
      json: [
        {
          id: "fixture-item",
          source_id: "test",
          url: "https://example.com",
          version,
        },
      ],
    }),
  );
  await page.route("**/api/versions/fixture-v1", (route) =>
    route.fulfill({
      json: { version, item: { url: "https://example.com" }, runs, reviews },
    }),
  );
  await page.route("**/api/versions/fixture-v1/reviews", async (route) => {
    const body = route.request().postDataJSON();
    expect(body.run_id).toBe("fixture-run");
    expect(body.reviewer).toBe("测试编辑");
    reviews.push({
      ...body,
      id: "fixture-review",
      created_at: version.captured_at,
    });
    await route.fulfill({ status: 201, json: reviews[0] });
  });
  await page.route("**/api/versions/fixture-v1/normalize", async (route) => {
    expect(route.request().postDataJSON().force).toBe(true);
    runs.unshift({
      ...run,
      id: "fixture-rerun",
      status: "pending",
      output: null,
    });
    await route.fulfill({ status: 202, json: { id: "fixture-rerun" } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Browser test fixture/ }).click();
  await expect(
    page.getByRole("button", { name: "提取符合原文" }),
  ).toBeDisabled();
  await page.getByLabel("复核人").fill("测试编辑");
  await page.getByLabel("核对结果").fill("对照 p0001，提取符合原文。");
  await page.getByRole("button", { name: "提取符合原文" }).click();
  await expect(
    page.getByRole("heading", { name: "人工复核历史" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "重新提取" }).click();
  await expect(page.getByText("等待处理", { exact: true })).toBeVisible();
  await expect(
    page.getByText("对照 p0001，提取符合原文。", { exact: true }),
  ).toBeVisible();
});

test("mobile layout stays within viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "从原始材料开始" }),
  ).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > innerWidth,
  );
  expect(overflow).toBe(false);
});
