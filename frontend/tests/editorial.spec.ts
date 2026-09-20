import { expect, test } from "@playwright/test";

test("editorial inbox opens against the real API without creating human records", async ({
  page,
}) => {
  await page.goto("/");
  const loaded = page.waitForResponse((response) =>
    response.url().includes("/api/editorial/events?"),
  );
  await page.getByRole("button", { name: "编辑收件箱" }).click();
  expect((await loaded).status()).toBe(200);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Editorial Inbox" }),
  ).toBeVisible();
  await page.getByText("新建事件骨架", { exact: true }).click();
  await expect(
    page.getByRole("button", { name: "创建事件", exact: true }),
  ).toBeDisabled();
  await page.screenshot({
    path: "../data/qa/editorial-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  await page.screenshot({
    path: "../data/qa/editorial-mobile.png",
    fullPage: true,
  });
});

test("editorial workflow shows independent gates, evidence checks and immutable review history", async ({
  page,
}) => {
  // Synthetic UI fixture: all editorial mutations are intercepted; none reaches the business DB.
  const event = {
    id: "fixture-event",
    title: "Editorial fixture",
    subject: "Authors",
    action: "release",
    object: "task queue",
    scope: "Fixture scope only",
    happened_at: null,
    event_version: null,
    revision: 2,
    value_status: "pending",
    quality_status: "pending",
    decision: "pending",
    created_at: "2026-09-21T00:00:00Z",
    updated_at: "2026-09-21T00:00:00Z",
  };
  const claim = {
    id: "fixture-claim",
    text: "Authors released a task queue",
    kind: "fact_candidate",
    critical: true,
  };
  const evidence = {
    id: "fixture-evidence",
    claim_id: claim.id,
    version_id: "fixture-version",
    paragraph_ids: ["p0001"],
    quote: "The release adds a task queue.",
    direction: "supporting",
    rationale: "Release description",
    source_root: "https://example.com/release",
    limitations: "Publisher only; no outcome proof",
    status: "unchecked",
    checked_by: null as string | null,
    checked_at: null as string | null,
    created_at: event.created_at,
  };
  const member = {
    id: "fixture-member",
    version_id: "fixture-version",
    paragraph_ids: ["p0001"],
    active: true,
    title: "Original fixture",
    source_name: "Publisher",
    url: "https://example.com/release",
    published_at: null,
    paragraphs: [{ id: "p0001", text: evidence.quote }],
  };
  const reviews: unknown[] = [];
  const submissions: string[] = [];
  await page.route("**/api/editorial/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: path.endsWith("/fixture-event")
          ? {
              event,
              members: [member],
              claims: [claim],
              evidence: [evidence],
              reviews,
              history: [],
              verified_source_roots: evidence.status === "verified" ? 1 : 0,
            }
          : { events: [event], total: 1, offset: 0, limit: 50 },
      });
      return;
    }
    const body = route.request().postDataJSON();
    expect(body.actor).toBe("测试编辑");
    expect(body.revision).toBe(event.revision);
    const action = path.split("/").pop()!;
    if (action === "decision" && event.quality_status !== "passed") {
      await route.fulfill({
        status: 422,
        json: { detail: "通过 Value Gate 和 Quality Gate 后才能入选" },
      });
      return;
    }
    submissions.push(action);
    if (action === "review") {
      expect(body.original_checked).toBe(true);
      evidence.status = body.status;
      evidence.checked_by = body.actor;
      evidence.checked_at = event.created_at;
      event.revision += 1;
      event.value_status = event.quality_status = event.decision = "pending";
    } else {
      if (action === "value") {
        expect(body.important).toBe(false);
        expect(body.useful).toBe(true);
        event.value_status = body.status;
      } else if (action === "quality") {
        expect(body.gaps).toEqual([]);
        event.quality_status = body.status;
      } else event.decision = body.status;
      reviews.unshift({
        id: `review-${reviews.length}`,
        revision: event.revision,
        gate: action,
        status: body.status,
        actor: body.actor,
        detail: body,
        created_at: event.created_at,
      });
    }
    await route.fulfill({ json: {} });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "编辑收件箱" }).click();
  await page.getByLabel("编辑姓名", { exact: true }).fill("测试编辑");
  await page.getByRole("button", { name: /Editorial fixture/ }).click();
  const panel = (name: string) =>
    page.getByText(name, { exact: true }).locator("..");
  const decision = panel("编辑决定");
  await decision.locator("summary").click();
  await decision.getByLabel("处理方式").selectOption("selected");
  await decision.getByLabel("本次操作依据").fill("Test selection");
  await decision.getByRole("button", { name: "保存编辑决定" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "通过 Value Gate 和 Quality Gate 后才能入选",
  );
  const verification = panel("核验此证据");
  await verification.locator("summary").click();
  await verification.getByRole("checkbox").check();
  await verification.getByLabel("证据核验结论").selectOption("verified");
  await verification
    .getByLabel("本次操作依据")
    .fill("Checked original release and conditions");
  await verification.getByRole("button", { name: "记录证据核验" }).click();
  await expect(page.getByText("已核验", { exact: true })).toBeVisible();
  const value = panel("价值门 · Important OR Useful");
  await value.locator("summary").click();
  await value.getByLabel("Useful 是否成立").selectOption("true");
  await value.getByLabel("实用性理由").fill("Bounded testable workflow");
  await value.getByLabel("价值判断", { exact: true }).selectOption("passed");
  await value
    .getByLabel("本次操作依据")
    .fill("Useful without broad industry impact");
  await value.getByRole("button", { name: "保存价值判断" }).click();
  await expect(page.getByText("价值：通过", { exact: true })).toBeVisible();
  await expect(page.getByText("质量：待判断", { exact: true })).toBeVisible();
  const quality = panel("质量门 · 证据充分吗");
  await quality.locator("summary").click();
  await quality.getByLabel("质量判断", { exact: true }).selectOption("passed");
  await quality
    .getByLabel("本次操作依据")
    .fill("All key claims traced to verified original");
  await quality.getByRole("button", { name: "保存质量判断" }).click();
  await expect(page.getByText("质量：通过", { exact: true })).toBeVisible();
  await decision.locator("summary").click();
  await decision.getByLabel("处理方式").selectOption("selected");
  await decision
    .getByLabel("本次操作依据")
    .fill("Ready for a separately reviewed Brief");
  await decision.getByRole("button", { name: "保存编辑决定" }).click();
  await expect(page.getByText("决定：入选", { exact: true })).toBeVisible();
  expect(submissions).toEqual(["review", "value", "quality", "decision"]);
  await page.screenshot({
    path: "../data/qa/editorial-fixture.png",
    fullPage: true,
  });
});
