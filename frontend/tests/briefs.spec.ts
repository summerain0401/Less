import { expect, test } from "@playwright/test";

test("Brief review UI requires explicit version actions and Today hides changed evidence", async ({
  page,
}) => {
  // Synthetic publication only: every /briefs write is intercepted.
  const brief = {
    id: "fixture-brief",
    event_id: "fixture-event",
    revision: 1,
    status: "draft",
    created_at: "2026-09-21T00:00:00Z",
  };
  const content = {
    title: "Fixture Brief",
    why_it_matters: "Useful for queue users",
    what_changed: "A queue was added",
    our_take: "Interpretation: test first",
    try_it: "",
    facts: [{ claim_id: "claim", evidence_ids: ["evidence"] }],
  };
  const sources = [
    {
      claim_id: "claim",
      claim: "The authors released a queue",
      kind: "reported_claim",
      evidence_id: "evidence",
      version_id: "fixture-version",
      paragraph_ids: ["p0001"],
      quote: "Queue released",
      direction: "supporting",
      limitations: "Publisher only",
      source_root: "fixture",
      url: "https://example.com",
    },
  ];
  const reviews: Record<string, unknown>[] = [];
  let published = false;
  const actions: string[] = [];
  await page.route("**/api/briefs**", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      expect(body.actor).toBe("Fixture editor");
      expect(body.revision).toBe(1);
      if (body.action === "approve") expect(body.original_checked).toBe(true);
      actions.push(body.action);
      brief.status = (
        {
          submit: "in_review",
          approve: "approved",
          publish: "published",
          withdraw: "withdrawn",
        } as Record<string, string>
      )[body.action];
      if (body.action === "publish") published = true;
      reviews.push({
        id: String(reviews.length),
        revision: 1,
        actor: body.actor,
        action: body.action,
        reason: body.reason,
        created_at: "2026-09-21T00:00:00Z",
      });
      return route.fulfill({ json: brief });
    }
    if (route.request().url().endsWith("/briefs"))
      return route.fulfill({ json: [brief] });
    return route.fulfill({
      json: {
        brief,
        versions: [
          {
            id: "version",
            revision: 1,
            event_revision: 1,
            content,
            sources,
            actor: "Fixture",
            reason: "Fixture only",
            created_at: "2026-09-21T00:00:00Z",
          },
        ],
        reviews,
        current_eligible: true,
      },
    });
  });
  await page.route("**/api/editorial/events**", async (route) => {
    if (new URL(route.request().url()).pathname.endsWith("fixture-event"))
      return route.fulfill({
        json: {
          event: {
            id: "fixture-event",
            revision: 1,
            title: "Fixture event",
            decision: "selected",
          },
          claims: [
            {
              id: "claim",
              text: "The authors released a queue",
              critical: true,
            },
          ],
          evidence: [
            {
              id: "evidence",
              claim_id: "claim",
              status: "verified",
              direction: "supporting",
              quote: "Queue released",
              limitations: "Publisher only",
            },
          ],
        },
      });
    return route.fulfill({ json: { events: [], total: 0 } });
  });
  await page.route("**/api/today**", (route) =>
    route.fulfill({
      json: {
        day: "2026-09-21",
        recorded: published,
        note: "Fixture only",
        readable_count: published && brief.status === "published" ? 1 : 0,
        entries: published
          ? [
              {
                brief_id: brief.id,
                revision: 1,
                status: brief.status,
                content: brief.status === "published" ? content : null,
                sources: brief.status === "published" ? sources : [],
              },
            ]
          : [],
      },
    }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: /Brief 与 Today/ }).click();
  await page.getByLabel("Brief 编辑姓名").fill("Fixture editor");
  await page.getByText("编辑 Brief", { exact: true }).click();
  await page.getByLabel("已保存 Brief").selectOption("fixture-brief");
  const perform = async (action: string) => {
    await page.getByLabel("Brief 操作").selectOption(action);
    await page.getByLabel("审核或发布依据").fill("Checked fixture only");
    if (action === "approve")
      await page.getByLabel("我已核对原文、事实与解释边界及新增价值").check();
    await page.getByRole("button", { name: "执行 Brief 操作" }).click();
    await expect.poll(() => actions.at(-1)).toBe(action);
  };
  await perform("submit");
  await expect(page.getByText(/当前状态：审核中/)).toBeVisible();
  await perform("approve");
  await expect(page.getByText(/当前状态：已批准/)).toBeVisible();
  await perform("publish");
  await expect(page.getByText("2026-09-21 · 1 条可读内容")).toBeVisible();
  await perform("withdraw");
  await expect(page.getByText(/原版本 1 暂不展示/)).toBeVisible();
  expect(actions).toEqual(["submit", "approve", "publish", "withdraw"]);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../data/qa/briefs-mobile-fixture.png",
    fullPage: true,
  });
});
