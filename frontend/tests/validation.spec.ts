import { expect, test } from "@playwright/test";

test("validation desk reads real daily metrics and frozen samples on desktop and mobile", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "验收台" }).click();
  await expect(
    page.getByRole("heading", { name: "每日运行与验收" }),
  ).toBeVisible();
  await expect(page.getByText("计划采集成功率", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "导出日报" })).toHaveAttribute(
    "href",
    /report\.md/,
  );
  await expect(
    page.getByRole("button", { name: "新建 30 条抽样" }),
  ).toBeDisabled();
  await expect(page.locator(".validation-desk .item-row")).toHaveCount(30);
  await page.screenshot({
    path: "../data/qa/validation-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  await page.locator(".validation-desk .item-row").first().click();
  await expect(page.getByText("逐字段核查", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "保存字段核查" }),
  ).toBeDisabled();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  await page.screenshot({
    path: "../data/qa/validation-mobile.png",
    fullPage: true,
  });
});

test("field review requires explicit original check, preserves edits on refresh, and binds exact run", async ({
  page,
}) => {
  // Test-only route interception; no fictional human reviews enter the real database.
  const batch = {
    id: "fixture-b",
    actor: "fixture",
    seed: "test",
    target_count: 30,
    population_count: 1,
    sample_count: 1,
    source_count: 1,
    created_at: "2026-09-20T01:00:00Z",
  };
  const sample = {
    id: "fixture-s",
    version_id: "fixture-v",
    run_id: "fixture-run",
    position: 0,
    source_name: "Fixture source",
    title: "Validation fixture",
    status: "succeeded",
    reviewed: false,
  };
  const fields = [
    { key: "title", label: "标题", value: sample.title, allows_unknown: false },
    { key: "author", label: "作者", value: null, allows_unknown: true },
  ];
  const reviews: unknown[] = [];
  let submissions = 0;
  await page.route("**/api/validation/batches", (route) =>
    route.fulfill({ json: [batch] }),
  );
  await page.route("**/api/validation/batches/fixture-b", (route) =>
    route.fulfill({ json: { batch, samples: [sample] } }),
  );
  await page.route("**/api/validation/samples/fixture-s", (route) =>
    route.fulfill({
      json: {
        sample,
        original: {
          id: "fixture-v",
          title: sample.title,
          url: "https://example.com",
          author: null,
          published_at: null,
          paragraphs: [{ id: "p0001", text: "Fixture original." }],
        },
        output: null,
        fields,
        reviews,
      },
    }),
  );
  await page.route(
    "**/api/validation/samples/fixture-s/reviews",
    async (route) => {
      const body = route.request().postDataJSON();
      expect(body.run_id).toBe("fixture-run");
      expect(body.original_checked).toBe(true);
      expect(body.fields).toEqual([
        { key: "title", verdict: "incorrect", note: "Fixture discrepancy" },
        { key: "author", verdict: "unknown_correct", note: "" },
      ]);
      submissions += 1;
      reviews.push({
        ...body,
        id: "fixture-review",
        created_at: batch.created_at,
      });
      await route.fulfill({ status: 201, json: reviews[0] });
    },
  );
  await page.goto("/");
  await page.getByRole("button", { name: "验收台" }).click();
  await page.getByLabel("操作人", { exact: true }).fill("测试编辑");
  await page.getByRole("button", { name: /Validation fixture/ }).click();
  const submit = page.getByRole("button", { name: "保存字段核查" });
  await expect(submit).toBeDisabled();
  await page
    .getByLabel("核查：标题", { exact: true })
    .selectOption("incorrect");
  await page
    .getByLabel("核查：作者", { exact: true })
    .selectOption("unknown_correct");
  await page.getByLabel("我已对照原始材料，判断以上字段").check();
  await expect(submit).toBeDisabled();
  await page
    .getByLabel("依据：标题", { exact: true })
    .fill("Fixture discrepancy");
  // Trigger another polling refresh without losing an in-progress assessment.
  await page.clock.install();
  await page.clock.fastForward(9000);
  await expect(page.getByLabel("依据：标题", { exact: true })).toHaveValue(
    "Fixture discrepancy",
  );
  await submit.click();
  await expect(
    page.getByText("字段核查已保存，历史记录保持可追溯"),
  ).toBeVisible();
  expect(submissions).toBe(1);
  await expect(page.getByText("字段核查历史 · 1 条")).toBeVisible();
});

test("work timing records scope and rejects incomplete or inconsistent counts", async ({
  page,
}) => {
  const sessions: unknown[] = [];
  let stopped = false;
  await page.route("**/api/validation/sessions", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      expect(body.mode).toBe("baseline");
      expect(body.category).toBe("screening");
      expect(body.source_ids).toEqual(["openai-codex"]);
      const session = {
        ...body,
        id: "fixture-session",
        started_at: "2026-09-20T01:00:00Z",
        ended_at: null,
        read_count: null,
        candidate_count: null,
        selected_count: null,
        note: null,
      };
      sessions.push(session);
      await route.fulfill({ status: 201, json: session });
    } else await route.fulfill({ json: sessions });
  });
  await page.route(
    "**/api/validation/sessions/fixture-session/stop",
    async (route) => {
      expect(route.request().postDataJSON()).toEqual({
        read_count: 5,
        candidate_count: 2,
        selected_count: 1,
        note: "Fixture selection",
      });
      stopped = true;
      await route.fulfill({ json: {} });
    },
  );
  await page.goto("/");
  await page.getByRole("button", { name: "验收台" }).click();
  await page
    .getByText("人工工作计时 · 基线与使用 Less 的对照", { exact: true })
    .click();
  const start = page.getByRole("button", { name: "开始计时" });
  await expect(start).toBeDisabled();
  await page.getByLabel("操作人", { exact: true }).fill("测试编辑");
  await page.getByRole("checkbox", { name: "OpenAI Codex Releases" }).check();
  await start.click();
  const stop = page.getByRole("button", { name: "结束并保存计时" });
  await expect(stop).toBeDisabled();
  await page.getByLabel("阅读量", { exact: true }).fill("1");
  await page.getByLabel("候选数", { exact: true }).fill("2");
  await page.getByLabel("入选数", { exact: true }).fill("1");
  await page.getByLabel("工作记录与可定位的结果").fill("Fixture selection");
  await expect(stop).toBeDisabled();
  await page.getByLabel("阅读量", { exact: true }).fill("5");
  await stop.click();
  await expect(page.getByText("本次工作记录已保存")).toBeVisible();
  expect(stopped).toBe(true);
});
