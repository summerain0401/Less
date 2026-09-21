import { expect, test } from "@playwright/test";

test("clustering suggestions, merge, restore and split retain explicit editor choices", async ({
  page,
}) => {
  // All clustering writes use synthetic route fixtures, never real editorial records.
  const base = {
    title: "Fixture release",
    subject: "Fixture authors",
    action: "release",
    object: "Task queue",
    scope: "Fixture scope",
    happened_at: null,
    event_version: null,
    lifecycle: "active",
    redirected_to: null as string | null,
    value_status: "pending",
    quality_status: "pending",
    decision: "pending",
    created_at: "2026-09-21T00:00:00Z",
    updated_at: "2026-09-21T00:00:00Z",
  };
  const left = { ...base, id: "left", revision: 2 };
  const right = {
    ...base,
    id: "right",
    title: "Fixture release follow-up",
    revision: 3,
  };
  const events = [left, right];
  const member = {
    id: "member-left",
    version_id: "version-left",
    paragraph_ids: ["p0001"],
    active: true,
    title: "Original release fixture",
    source_name: "Fixture source",
    url: "https://example.com/release",
    published_at: null,
    paragraphs: [{ id: "p0001", text: "A release description." }],
  };
  const claim = {
    id: "claim-left",
    text: "The authors announced a release",
    kind: "reported_claim",
    critical: true,
  };
  let claims = [claim];
  const operations: Record<string, unknown>[] = [];
  const actions: string[] = [];
  await page.route("**/api/editorial/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() === "GET") {
      if (path.endsWith("/cluster-suggestions")) {
        await route.fulfill({
          json: {
            method: "event-skeleton-rules-v1",
            considered_events: 2,
            total_events: 2,
            total_pairs: 1,
            limitations: ["Test fixture; rule retrieval only"],
            pairs: [
              {
                left,
                right,
                score: 0.8,
                suggestion: "different",
                reasons: ["Shared subject"],
                conflicts: ["版本或范围标识不同"],
                shared_version_ids: [],
              },
            ],
          },
        });
      } else if (path.endsWith("/events")) {
        const active = events.filter((e) => e.lifecycle === "active");
        await route.fulfill({
          json: { events: active, total: active.length, offset: 0, limit: 50 },
        });
      } else {
        const event = events.find((e) => e.id === path.split("/").pop());
        await route.fulfill({
          json: {
            event,
            members: [member],
            claims,
            evidence: [],
            reviews: [],
            history: [],
            verified_source_roots: 0,
            cluster_operations: operations,
          },
        });
      }
      return;
    }
    const body = route.request().postDataJSON();
    expect(body.actor).toBe("测试编辑");
    if (path.endsWith("/merge")) {
      expect(body.target_id).toBe("left");
      expect(body.events).toEqual([
        { id: "left", revision: 2 },
        { id: "right", revision: 3 },
      ]);
      actions.push("merge");
      left.revision += 1;
      right.revision += 1;
      right.lifecycle = "merged";
      right.redirected_to = "left";
      operations.unshift({
        id: "merge-op",
        kind: "merge",
        actor: body.actor,
        reason: body.reason,
        after_revisions: { left: left.revision, right: right.revision },
        created_event_ids: [],
        status: "applied",
        created_at: base.created_at,
        restored_at: null,
        restored_by: null,
        restore_reason: null,
      });
    } else if (path.endsWith("/restore")) {
      expect(body.reason).toBe("Fixture grouping was too broad");
      actions.push("restore");
      left.revision += 1;
      right.revision += 1;
      right.lifecycle = "active";
      right.redirected_to = null;
      Object.assign(operations[0], {
        status: "restored",
        restored_by: body.actor,
        restore_reason: body.reason,
        restored_at: base.created_at,
      });
    } else if (path.endsWith("/split")) {
      expect(body.revision).toBe(left.revision);
      expect(body.member_ids).toEqual(["member-left"]);
      expect(body.claim_ids).toEqual(["claim-left"]);
      expect(body.target.title).toBe("Independent evaluation fixture");
      actions.push("split");
      left.revision += 1;
      member.active = false;
      claims = [];
      events.push({
        ...base,
        id: "split-result",
        title: body.target.title,
        revision: 2,
      });
      operations.unshift({
        id: "split-op",
        kind: "split",
        actor: body.actor,
        reason: body.reason,
        after_revisions: { left: left.revision, "split-result": 2 },
        created_event_ids: ["split-result"],
        status: "applied",
        created_at: base.created_at,
        restored_at: null,
        restored_by: null,
        restore_reason: null,
      });
    } else throw new Error(`Unexpected fixture mutation: ${path}`);
    await route.fulfill({ status: 201, json: operations[0] });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "编辑收件箱" }).click();
  await page.getByLabel("编辑姓名", { exact: true }).fill("测试编辑");
  await page.getByText("事件聚类建议 · 先检查差异", { exact: true }).click();
  await page.getByRole("button", { name: "刷新聚类建议" }).click();
  await expect(
    page.getByText("版本或范围标识不同", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Fixture release", exact: true })
    .click();
  const panel = (name: string) =>
    page.getByText(name, { exact: true }).locator("..");
  await page.getByText("合并、拆分与恢复", { exact: true }).click();
  const merge = panel("与其他事件合并");
  await merge.locator("summary").click();
  await expect(
    merge.getByRole("button", { name: "合并选中事件" }),
  ).toBeDisabled();
  await merge
    .getByRole("checkbox", { name: /Fixture release follow-up/ })
    .check();
  await merge
    .getByLabel("合并依据", { exact: true })
    .fill("Same release fixture");
  await page.screenshot({
    path: "../data/qa/cluster-merge-fixture.png",
    fullPage: true,
  });
  await merge.getByRole("button", { name: "合并选中事件" }).click();
  await page.getByText("合并、拆分与恢复", { exact: true }).click();
  await expect(page.getByText("合并 · 已应用", { exact: true })).toBeVisible();
  await page
    .getByLabel("恢复依据", { exact: true })
    .fill("Fixture grouping was too broad");
  await page.getByRole("button", { name: "恢复本次聚类操作" }).click();
  await page.getByText("合并、拆分与恢复", { exact: true }).click();
  await expect(page.getByText("合并 · 已恢复", { exact: true })).toBeVisible();
  const split = panel("拆出独立事件");
  await split.locator("summary").click();
  await split
    .getByRole("checkbox", { name: "Original release fixture" })
    .check();
  await split
    .getByRole("checkbox", { name: "The authors announced a release" })
    .check();
  await split
    .getByLabel("事件标题", { exact: true })
    .fill("Independent evaluation fixture");
  await split
    .getByLabel("本次操作依据", { exact: true })
    .fill("A later independent evaluation");
  await split.getByRole("button", { name: "创建拆分事件" }).click();
  await page.getByText("合并、拆分与恢复", { exact: true }).click();
  await expect(page.getByText("拆分 · 已应用", { exact: true })).toBeVisible();
  expect(actions).toEqual(["merge", "restore", "split"]);
  await page.screenshot({
    path: "../data/qa/cluster-history-fixture.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  await page.screenshot({
    path: "../data/qa/cluster-mobile-fixture.png",
    fullPage: true,
  });
});
