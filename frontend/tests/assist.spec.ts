import { expect, test } from "@playwright/test";

test("machine value tasks and blind exclusion audits keep human decisions separate", async ({
  page,
}) => {
  const event = { id: "event", revision: 2, title: "Fixture event" };
  const input = {
    events: [
      {
        ...event,
        materials: [
          {
            version_id: "version",
            title: "Fixture original",
            url: "https://example.com",
            paragraphs: [{ id: "p1", text: "Fixture original paragraph" }],
          },
        ],
      },
    ],
  };
  const proposal = {
    important: 0,
    useful: 1,
    important_reason: "Narrow scope",
    useful_reason: "PRIVATE_MACHINE_REASON",
    uncertain: false,
    limitations: [],
  };
  const run = {
    id: "run",
    stage: "value",
    prompt_version: "fixture",
    model: "fixture",
    input,
    status: "succeeded",
    attempts: 1,
    created_at: "2026-09-21T00:00:00Z",
    output: proposal,
    error: null,
    applied_event_id: null,
  };
  const reviews: Record<string, unknown>[] = [];
  let queued = false;
  await page.route("**/api/editorial/events**", (route) =>
    route.fulfill({ json: { events: [event], total: 1 } }),
  );
  await page.route("**/api/assist**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      expect(body.actor).toBe("Fixture editor");
      if (path === "/api/assist") {
        expect(body.stage).toBe("value");
        expect(body.event_ids).toEqual(["event"]);
        queued = true;
        return route.fulfill({ status: 201, json: run });
      }
      if (path.endsWith("/reviews")) {
        expect(body.expected_revision).toBe(reviews.length);
        expect(body.original_checked).toBe(true);
        reviews.push({ ...body, revision: reviews.length + 1 });
        return route.fulfill({
          status: 201,
          json: { revision: reviews.length },
        });
      }
      return route.fulfill({ status: 201, json: { id: 77 } });
    }
    if (path.endsWith("candidates"))
      return route.fulfill({
        json: {
          rows: [],
          unassessed_events: 1,
          method: "Fixture only",
          limitations: "Fixture only",
        },
      });
    if (path.endsWith("/audits"))
      return route.fulfill({
        json: [{ id: 77, seed: "fixed", pool: "excluded", sample_count: 1 }],
      });
    if (path.endsWith("/audits/77"))
      return route.fulfill({
        json: {
          id: 77,
          pool: "excluded",
          target_count: 20,
          population: 1,
          limitations: "Fixed fixture",
          samples: [
            {
              run_id: "run",
              input,
              proposal: reviews.length ? proposal : null,
              reviews,
            },
          ],
          blind_counts: {
            reviewed: reviews.length ? 1 : 0,
            value: reviews.length ? 1 : 0,
          },
          latest_counts: {
            reviewed: reviews.length ? 1 : 0,
            value: reviews.length ? 1 : 0,
          },
        },
      });
    return route.fulfill({ json: queued ? [run] : [] });
  });
  await page.goto("/");
  await page.getByRole("button", { name: /机器辅助 08/ }).click();
  await page.getByLabel("操作人", { exact: true }).fill("Fixture editor");
  await page.getByRole("combobox", { name: "辅助任务", exact: true }).selectOption("value");
  await page.getByLabel("Fixture event", { exact: true }).check();
  await page.getByRole("button", { name: "加入处理队列" }).click();
  await expect(page.getByRole("status")).toContainText("任务已入队");
  await page.getByText("候选认可与机器漏选审计", { exact: true }).click();
  await page.getByRole("button", { name: "读取价值审计批次" }).click();
  await page.getByRole("combobox", { name: "价值审计批次", exact: true }).selectOption("77");
  await expect(page.getByText("提交首次判断后显示机器理由。")).toBeVisible();
  const audit = page
    .locator("details.work-panel")
    .filter({
      has: page.locator("summary", { hasText: "候选认可与机器漏选审计" }),
    });
  await expect(audit.getByText("PRIVATE_MACHINE_REASON")).toHaveCount(0);
  await page.getByLabel("已对照原文独立判断价值").check();
  await page.getByRole("combobox", { name: "人工价值审计", exact: true }).selectOption("value");
  await page.getByLabel("审计重要性理由").fill("Limited importance");
  await page.getByLabel("审计实用性理由").fill("Useful for bounded tasks");
  await page.getByRole("button", { name: "保存价值盲判" }).click();
  await expect(audit.getByText("Useful：PRIVATE_MACHINE_REASON")).toBeVisible();
  await expect(
    audit.getByText(/判断 1 · Fixture editor · 具备价值/),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../data/qa/assist-mobile-fixture.png",
    fullPage: true,
  });
});
