import { expect, test } from "@playwright/test";

const draft = {
  id: "fixture-brief",
  title: "Agents gain resumable tasks",
  published_at: "2026-09-22",
  topics: ["Agents"],
  important: true,
  useful: true,
  confidence: "high",
  sources: [
    {
      name: "Fixture release",
      url: "https://example.com/fixture-release",
      type: "release",
      primary: true,
      published_at: "2026-09-22T09:00:00+08:00",
    },
  ],
  what_happened: "A verified fixture release added resumable tasks.",
  why_it_matters: "Agent users can continue interrupted work instead of starting over.",
  our_take: "This matters most for long-running local workflows.",
  uncertainty: null,
};

test("reader flow and structured draft management", async ({ page }) => {
  let briefs = [{ ...draft, created_at: "2026-09-22T02:00:00Z", updated_at: null }];

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/today") {
      return route.fulfill({ json: { day: url.searchParams.get("day"), entries: briefs } });
    }
    if (url.pathname === "/api/topics") {
      return route.fulfill({ json: briefs.length ? [{ id: "agents", name: "Agents", brief_count: briefs.length }] : [] });
    }
    if (url.pathname === "/api/briefs" && request.method() === "GET") {
      return route.fulfill({ json: briefs });
    }
    if (url.pathname === "/api/briefs" && request.method() === "POST") {
      const body = request.postDataJSON();
      expect(body.id).toBe("second-brief");
      const created = { ...body, created_at: "2026-09-22T03:00:00Z", updated_at: null };
      briefs = [created, ...briefs];
      return route.fulfill({ status: 201, json: created });
    }
    if (url.pathname === "/api/briefs/second-brief" && request.method() === "PUT") {
      const body = request.postDataJSON();
      const changed = { ...body, id: "second-brief", created_at: briefs[0].created_at, updated_at: "2026-09-22T04:00:00Z" };
      briefs[0] = changed;
      return route.fulfill({ json: changed });
    }
    if (url.pathname === "/api/briefs/second-brief" && request.method() === "DELETE") {
      briefs = briefs.filter((brief) => brief.id !== "second-brief");
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({ status: 404, json: { detail: "Not found" } });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Agents gain resumable tasks" })).toBeVisible();
  await page.getByRole("button", { name: "阅读全文" }).click();
  await expect(page.getByRole("heading", { name: "发生了什么" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Fixture release/ })).toHaveAttribute("href", draft.sources[0].url);
  await page.getByRole("button", { name: "返回" }).click();

  await page.getByRole("button", { name: "管理" }).click();
  await page.getByLabel("Brief JSON").fill("{");
  await expect(page.getByRole("alert")).toContainText("JSON 格式无效");

  const second = { ...draft, id: "second-brief", title: "Second useful Brief" };
  await page.getByLabel("Brief JSON").fill(JSON.stringify(second, null, 2));
  await expect(page.getByText("结构检查通过，可以预览并保留。")).toBeVisible();
  await page.getByRole("button", { name: "确认保留" }).click();
  await expect(page.getByText("Brief 已保留并进入今天")).toBeVisible();
  await expect(page.getByText("Second useful Brief", { exact: true })).toBeVisible();

  const row = page.locator(".saved-row").filter({ hasText: "Second useful Brief" });
  await row.getByRole("button", { name: "编辑" }).click();
  const corrected = { ...second, title: "Corrected useful Brief" };
  delete (corrected as Partial<typeof second>).id;
  await page.getByLabel("Brief JSON").fill(JSON.stringify(corrected, null, 2));
  await page.getByRole("button", { name: "保存更正" }).click();
  await expect(page.getByText("更正已保存")).toBeVisible();
  await expect(page.getByText("Corrected useful Brief", { exact: true })).toBeVisible();

  page.on("dialog", (dialog) => dialog.accept());
  await page.locator(".saved-row").filter({ hasText: "Corrected useful Brief" }).getByRole("button", { name: "删除" }).click();
  await expect(page.getByText("Brief 已移除")).toBeVisible();
  await expect(page.getByText("Corrected useful Brief", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "Topics" }).click();
  await expect(page.getByRole("button", { name: /Agents/ })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("skip clears an unsaved draft without a write", async ({ page }) => {
  let writes = 0;
  await page.route("**/api/**", async (route) => {
    if (route.request().method() !== "GET") writes += 1;
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/briefs") return route.fulfill({ json: [] });
    if (path === "/api/topics") return route.fulfill({ json: [] });
    return route.fulfill({ json: { day: "2026-09-22", entries: [] } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "管理" }).click();
  await page.getByRole("button", { name: "跳过 / 清空" }).click();
  await expect(page.getByText("草稿已跳过，未写入内容库")).toBeVisible();
  expect(writes).toBe(0);
});

test("imports an array of Briefs with one confirmation", async ({ page }) => {
  const saved: (typeof draft & { created_at: string; updated_at: null })[] = [];
  const posted: string[] = [];
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/today") return route.fulfill({ json: { day: "2026-09-22", entries: saved } });
    if (path === "/api/briefs" && request.method() === "GET") return route.fulfill({ json: saved });
    if (path === "/api/briefs" && request.method() === "POST") {
      const body = request.postDataJSON();
      expect(Array.isArray(body)).toBe(false);
      posted.push(body.id);
      const created = { ...body, created_at: "2026-09-22T03:00:00Z", updated_at: null };
      saved.push(created);
      return route.fulfill({ status: 201, json: created });
    }
    return route.fulfill({ json: [] });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "管理" }).click();
  const drafts = [
    { ...draft, id: "batch-first", title: "First batch Brief" },
    { ...draft, id: "batch-second", title: "Second batch Brief", sources: [{ ...draft.sources[0], url: "https://example.com/second" }] },
  ];
  await page.getByLabel("Brief JSON").fill(JSON.stringify(drafts));
  await expect(page.getByText("2 条草稿结构检查通过，可以预览并保留。")).toBeVisible();
  await expect(page.locator(".preview-item")).toHaveCount(2);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button", { name: "确认保留 2 条" }).click();
  await expect(page.getByText("2 条 Brief 已保留并进入今天")).toBeVisible();
  expect(posted).toEqual(["batch-first", "batch-second"]);
  await page.getByRole("button", { name: "Today" }).click();
  await expect(page.getByRole("heading", { name: "First batch Brief" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Second batch Brief" })).toBeVisible();
});

test("rejects empty and duplicate-id arrays before saving", async ({ page }) => {
  let writes = 0;
  await page.route("**/api/**", async (route) => {
    if (route.request().method() !== "GET") writes += 1;
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/today") return route.fulfill({ json: { day: "2026-09-22", entries: [] } });
    return route.fulfill({ json: [] });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "管理" }).click();
  await page.getByLabel("Brief JSON").fill("[]");
  await expect(page.getByRole("alert")).toContainText("Brief 数组不能为空");
  await page.getByLabel("Brief JSON").fill(JSON.stringify([draft, { ...draft, title: "Duplicate" }]));
  await expect(page.getByRole("alert")).toContainText("第 2 条：id fixture-brief 在本次数组中重复");
  await expect(page.getByRole("button", { name: /确认保留/ })).toBeDisabled();
  expect(writes).toBe(0);
});

test("keeps unsaved array entries after a partial failure", async ({ page }) => {
  const saved: (typeof draft & { created_at: string; updated_at: null })[] = [];
  const posted: string[] = [];
  let failed = false;
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/today") return route.fulfill({ json: { day: "2026-09-22", entries: saved } });
    if (path === "/api/briefs" && request.method() === "GET") return route.fulfill({ json: saved });
    if (path === "/api/briefs" && request.method() === "POST") {
      const body = request.postDataJSON();
      posted.push(body.id);
      if (body.id === "batch-second" && !failed) {
        failed = true;
        return route.fulfill({ status: 409, json: { detail: "临时冲突" } });
      }
      const created = { ...body, created_at: "2026-09-22T03:00:00Z", updated_at: null };
      saved.push(created);
      return route.fulfill({ status: 201, json: created });
    }
    return route.fulfill({ json: [] });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "管理" }).click();
  const drafts = ["batch-first", "batch-second", "batch-third"].map((id) => ({ ...draft, id, title: id }));
  await page.getByLabel("Brief JSON").fill(JSON.stringify(drafts));
  await page.getByRole("button", { name: "确认保留 3 条" }).click();
  await expect(page.getByText("已保留 1 条；剩余 2 条草稿仍在输入框中。")).toBeVisible();
  await expect(page.getByText("第 2 条保存失败：临时冲突")).toBeVisible();
  expect(JSON.parse(await page.getByLabel("Brief JSON").inputValue()).map((item: typeof draft) => item.id)).toEqual(["batch-second", "batch-third"]);
  await page.getByRole("button", { name: "确认保留 2 条" }).click();
  await expect(page.getByText("2 条 Brief 已保留并进入今天")).toBeVisible();
  expect(posted).toEqual(["batch-first", "batch-second", "batch-second", "batch-third"]);
});

test("shows the full multi-paragraph facts in detail and draft preview", async ({ page }) => {
  const facts = "此前，任务中断后需要重新开始，用户无法沿用已完成的步骤。\n\n这次发布增加了恢复入口：用户可以继续先前的任务，但仅限桌面端的指定版本；移动端尚未开放。";
  const detailed = { ...draft, what_happened: facts, created_at: "2026-09-22T02:00:00Z", updated_at: null };
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/today") return route.fulfill({ json: { day: "2026-09-22", entries: [detailed] } });
    if (path === "/api/briefs") return route.fulfill({ json: [detailed] });
    return route.fulfill({ json: [] });
  });
  await page.goto("/");
  await expect(page.locator(".brief-card .what")).toHaveCSS("-webkit-line-clamp", "5");
  await page.getByRole("button", { name: "阅读全文" }).click();
  await expect(page.locator(".detail-page .fact-body")).toHaveText(facts);
  await expect(page.locator(".detail-page .fact-body")).toHaveCSS("white-space", "pre-line");
  await page.getByRole("button", { name: "返回" }).click();
  await page.getByRole("button", { name: "管理" }).click();
  await page.getByLabel("Brief JSON").fill(JSON.stringify({ ...draft, what_happened: facts }));
  await expect(page.locator(".draft-preview .fact-body")).toHaveText(facts);
  await expect(page.locator(".draft-preview .fact-body")).toHaveCSS("white-space", "pre-line");
});
