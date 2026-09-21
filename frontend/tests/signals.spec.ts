import { expect, test } from "@playwright/test";

test("Signal records counter search and explicit weakening without rewriting its thesis", async ({
  page,
}) => {
  const signal = {
    id: "signal-fixture",
    revision: 2,
    status: "candidate",
    needs_review: true,
    last_reviewed_at: null as string | null,
    created_at: "2026-09-21T00:00:00Z",
    thesis: {
      title: "Fixture hypothesis",
      statement: "Bounded delegation may help",
      scope: "Unit-test tasks",
      starts_on: "2026-09-21",
      ends_on: "2026-09-28",
      falsification: "Review costs exceed savings",
      counter_plan: "Look for failures",
      owner: "Fixture editor",
    },
  };
  const records: Record<string, unknown>[] = [];
  const evidence = [
    {
      id: "link",
      evidence_id: "evidence",
      event_id: "event",
      event_revision: 1,
      direction: "counter",
      rationale: "Review cost may offset savings",
      active: true,
      added_at: "2026-09-21T00:00:00Z",
      snapshot: {
        claim: "Review cost rose in fixture",
        quote: "Fixture quote",
        version_id: "version",
        paragraph_ids: ["p0001"],
        source_root: "independent-fixture",
        limitations: "Fixture only",
        url: "https://example.com",
        happened_at: null,
      },
    },
  ];
  await page.route("**/api/signals**", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      expect(body.actor).toBe("Fixture editor");
      expect(body.revision).toBe(signal.revision);
      const kind = route.request().url().endsWith("searches")
        ? "counter_search"
        : "review";
      if (kind === "review") {
        expect(body.original_checked).toBe(true);
        expect(body.counter_resolutions).toEqual({
          link: "Scope weakened by higher review cost",
        });
        signal.status = body.status;
        signal.needs_review = false;
        signal.last_reviewed_at = "2026-09-21T01:00:00Z";
      }
      signal.revision += 1;
      records.push({
        id: String(records.length),
        revision: signal.revision,
        kind,
        actor: body.actor,
        reason: body.reason,
        detail: { previous_status: "candidate", ...body },
        created_at: "2026-09-21T01:00:00Z",
      });
      return route.fulfill({ json: signal });
    }
    return route.fulfill({
      json: route.request().url().endsWith("/signals")
        ? [signal]
        : { signal, evidence, records, stale_link_ids: [] },
    });
  });
  await page.route("**/api/editorial/events**", (route) =>
    route.fulfill({ json: { events: [], total: 0 } }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: /Signal 07/ }).click();
  await page.getByLabel("Signal 编辑姓名").fill("Fixture editor");
  await page.getByLabel("选择 Signal").selectOption("signal-fixture");
  await page.getByText("记录本轮反证检索", { exact: true }).click();
  await page.getByLabel("实际检索词").fill("agent review cost failures");
  await page
    .getByLabel("查阅来源类型与范围")
    .fill("Independent engineering reports; fixture");
  await page
    .getByLabel("发现、具体出处或未找到结果")
    .fill("Synthetic counter example");
  await page.getByLabel("检索缺口与覆盖限制").fill("Fixture not real research");
  const searches = page
    .locator("details")
    .filter({ has: page.locator("summary", { hasText: "记录本轮反证检索" }) })
    .first();
  await searches.getByLabel("本次变更依据").fill("Fixture search log");
  await page.getByRole("button", { name: "保存反证检索记录" }).click();
  await expect.poll(() => records.length).toBe(1);
  await page.getByText("人工复评与 Our View", { exact: true }).click();
  await page.getByLabel("复评后状态").selectOption("weakening");
  await page
    .getByLabel("Our View · 当前判断与未知")
    .fill("Scope needs narrowing");
  await page
    .getByLabel("来源独立性与证据适用范围", { exact: true })
    .fill("One independent fixture");
  await page.getByLabel("主要替代解释").fill("Novelty or task selection");
  await page
    .getByLabel("反证处理：Review cost may offset savings")
    .fill("Scope weakened by higher review cost");
  const review = page
    .locator("details")
    .filter({
      has: page.locator("summary", { hasText: "人工复评与 Our View" }),
    })
    .first();
  await review.getByLabel("本次变更依据").fill("Negative result narrows scope");
  await expect(
    page.getByRole("button", { name: "记录本轮复评" }),
  ).toBeDisabled();
  await page.getByLabel("已复核原文、独立性和适用范围").check();
  await page.getByRole("button", { name: "记录本轮复评" }).click();
  await expect(
    page.getByText("Weakening · 版本 4 · 已完成本轮复评"),
  ).toBeVisible();
  expect(signal.thesis.statement).toBe("Bounded delegation may help");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../data/qa/signal-mobile-fixture.png",
    fullPage: true,
  });
});
