import { expect, test } from "@playwright/test";

test("audit keeps prediction hidden before annotation and retains correction history", async ({
  page,
}) => {
  const batch = {
    id: "audit-fixture",
    seed: "fixture",
    actor: "Fixture",
    purpose: "development",
    method: "event-skeleton-rules-v1",
    target_count: 30,
    population_events: 2,
    considered_events: 2,
    population_pairs: 1,
    created_at: "2026-09-21T00:00:00Z",
  };
  const frozen = {
    event: {
      title: "Fixture release",
      subject: "Fixture authors",
      action: "release",
      object: "Queue",
      scope: "Test only",
      event_version: null,
      happened_at: null,
    },
    materials: [
      {
        version_id: "fixture",
        title: "Original",
        url: "https://example.com",
        source: "Fixture",
        paragraphs: [{ id: "p0001", text: "Fixture original text" }],
      },
    ],
  };
  const labels: Record<string, unknown>[] = [];
  const metrics = {
    reviewed: 0,
    wrong_merge: 0,
    wrong_split: 0,
    machine_abstained: 0,
    same_without_positive_suggestion: 0,
    evaluated: 0,
    error_rate: null,
    decision_coverage: null,
  };
  await page.route("**/api/editorial/cluster-audits**", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      expect(body.actor).toBe("测试编辑");
      expect(body.expected_revision).toBe(labels.length);
      expect(body.original_checked).toBe(true);
      labels.push({
        id: `label-${labels.length}`,
        revision: labels.length + 1,
        ...body,
        created_at: "2026-09-21T00:00:00Z",
      });
      return route.fulfill({ status: 201, json: labels.at(-1) });
    }
    if (route.request().url().endsWith("cluster-audits"))
      return route.fulfill({ json: [batch] });
    return route.fulfill({
      json: {
        batch,
        metrics,
        blind_metrics: metrics,
        limitations: ["Fixture only"],
        pairs: [
          {
            id: "pair",
            position: 1,
            snapshot: { left: frozen, right: frozen },
            prediction: labels.length
              ? {
                  suggestion: "same_candidate",
                  reasons: ["MACHINE_SECRET_REASON"],
                  conflicts: [],
                }
              : null,
            labels,
          },
        ],
      },
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: /编辑收件箱/ }).click();
  await page.getByLabel("编辑姓名").fill("测试编辑");
  await page.getByText("聚类抽样与盲判", { exact: true }).click();
  await page.getByRole("button", { name: "读取抽样批次" }).click();
  await page.getByLabel("选择抽样批次").selectOption("audit-fixture");
  await expect(page.getByText("提交首次判断后显示机器结果。")).toBeVisible();
  await expect(page.getByText("MACHINE_SECRET_REASON")).toHaveCount(0);
  await page.getByLabel("人工配对判断").selectOption("different");
  await page.getByLabel("配对判断依据").fill("不同发布范围，测试夹具");
  await page.getByLabel("我已核对两侧原文与事件边界").check();
  await page.getByRole("button", { name: "保存首次盲判" }).click();
  await expect(page.getByText("MACHINE_SECRET_REASON")).toBeVisible();
  await page.getByLabel("人工配对判断").selectOption("same");
  await page.getByLabel("配对判断依据").fill("补查范围后更正，测试夹具");
  await page.getByLabel("我已核对两侧原文与事件边界").check();
  await page.getByRole("button", { name: "保存判断更正" }).click();
  await expect(
    page.getByText("判断 1 · 不同事件", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("判断 2 · 同一事件", { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../data/qa/cluster-audit-mobile-fixture.png",
    fullPage: true,
  });
});
