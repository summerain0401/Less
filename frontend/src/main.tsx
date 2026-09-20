import React, { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import type { Check, Detail, Item, Overview, Run, Source } from "./types";
import { ValidationDesk } from "./ValidationDesk";
import { EditorialInbox } from "./EditorialInbox";
import "./style.css";

const time = (value: string | null) =>
  value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "未知";
const labels: Record<string, string> = {
  pending: "等待处理",
  running: "处理中",
  succeeded: "已完成",
  failed: "失败",
  retryable: "等待重试",
  budget_wait: "等待次日额度",
  blocked: "已暂停",
  missed: "漏执行",
  active: "启用",
  paused: "暂停",
  needs_review: "待复核",
};
function Status({ value }: { value: string }) {
  return <span className={`status ${value}`}>{labels[value] || value}</span>;
}
async function api<T>(
  path: string,
  body?: unknown,
  method = "POST",
): Promise<T> {
  const response = await fetch(
    `/api${path}`,
    body === undefined
      ? {}
      : {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : `请求失败 (${response.status})`,
    );
  }
  return response.json();
}

function App() {
  const [tab, setTab] = useState("items");
  const [sources, setSources] = useState<Source[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [checks, setChecks] = useState<Check[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewer, setReviewer] = useState("");
  const [note, setNote] = useState("");
  const refresh = useCallback(async () => {
    const [o, s, i, c, r] = await Promise.all([
      api<Overview>("/overview"),
      api<Source[]>("/sources"),
      api<Item[]>("/items"),
      api<Check[]>("/checks"),
      api<Run[]>("/runs"),
    ]);
    setOverview(o);
    setSources(s);
    setItems(i);
    setChecks(c);
    setRuns(r);
    if (selected) setDetail(await api<Detail>(`/versions/${selected}`));
  }, [selected]);
  useEffect(() => {
    let mounted = true;
    const update = () =>
      refresh().catch((e) => {
        if (mounted) setError(e.message);
      });
    void update();
    const timer = setInterval(update, 5000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [refresh]);
  async function action(fn: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
      await refresh();
      setNotice(message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const latest = detail?.runs[0];
  function review(decision: string) {
    if (!selected || !latest) return;
    void action(
      () =>
        api(`/versions/${selected}/reviews`, {
          run_id: latest.id,
          reviewer,
          decision,
          note,
        }),
      "复核记录已保存",
    );
  }
  return (
    <div className="app">
      <aside>
        <a className="brand" href="/">
          Less<span>Read less. Know more.</span>
        </a>
        <div className="workspace-label">EDITORIAL WORKSPACE</div>
        <nav>
          {[
            ["items", "原始材料", "01"],
            ["sources", "来源管理", "02"],
            ["activity", "运行记录", "03"],
            ["validation", "验收台", "04"],
            ["editorial", "编辑收件箱", "05"],
          ].map(([id, label, n]) => (
            <button
              key={id}
              className={tab === id ? "selected" : ""}
              onClick={() => {
                setTab(id);
                setSelected(null);
                setDetail(null);
              }}
            >
              <span>{label}</span>
              <small>{n}</small>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="dot" /> 本地工作台
          <br />
          <small>PHASE 1 / WEEK 1–2</small>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <div className="eyebrow">LESS INTELLIGENCE ENGINE</div>
            <h1>
              {tab === "items"
                ? "从原始材料开始"
                : tab === "sources"
                  ? "好的判断，始于好的来源"
                  : tab === "validation"
                    ? "让每一项进展都有依据"
                    : tab === "editorial"
                      ? "把材料变成可核查的事件"
                      : "每一步都有记录"}
            </h1>
            <p>
              {tab === "items"
                ? "查看出处、比对提取结果，为后续编辑留下可靠依据。"
                : tab === "sources"
                  ? "围绕 AI Coding 与 Agents，持续校准我们的观察范围。"
                  : tab === "validation"
                    ? "从跨来源抽查到人工工作计时，逐项检验第一周的运行质量。"
                    : tab === "editorial"
                      ? "写清楚价值理由，逐条核对证据，再作出编辑决定。"
                      : "区分无更新、失败与漏执行，保留真实的运行过程。"}
            </p>
          </div>
          <span className="phase">
            内部 · {tab === "editorial" ? "Week 2" : "Week 1"}
          </span>
        </header>
        {error && (
          <div role="alert" className="banner error">
            {error}
            <button onClick={() => setError("")}>关闭</button>
          </div>
        )}
        {notice && (
          <div role="status" className="banner">
            {notice}
          </div>
        )}
        {overview?.ai.paused && (
          <div className="banner error">
            AI 处理已暂停：{overview.ai.reason}
            <button
              disabled={busy}
              onClick={() =>
                void action(
                  () => api("/ai/resume", { actor: "local-editor" }),
                  "AI 队列已恢复",
                )
              }
            >
              恢复处理
            </button>
          </div>
        )}
        <section className="metrics">
          {[
            [
              "已接通来源",
              `${overview?.counts.connected_sources ?? 0} / ${overview?.counts.sources ?? 0}`,
            ],
            ["原始材料", overview?.counts.items ?? 0],
            ["保存版本", overview?.counts.versions ?? 0],
            ["AI 处理记录", overview?.counts.runs ?? 0],
          ].map(([k, v]) => (
            <div key={k}>
              <span>{k}</span>
              <strong>{v}</strong>
            </div>
          ))}
        </section>
        {tab === "validation" && <ValidationDesk sources={sources} />}
        {tab === "editorial" && <EditorialInbox items={items} />}
        {tab === "items" && !selected && (
          <section>
            <div className="section-heading">
              <h2>材料收件箱</h2>
              <span>最近 100 个版本 · 自动刷新</span>
            </div>
            {!items.length ? (
              <div className="empty">
                <h3>等待第一份值得阅读的材料</h3>
                <p>到来源管理发起采集，随后在这里查看原文和提取结果。</p>
                <button onClick={() => setTab("sources")}>查看来源</button>
              </div>
            ) : (
              <div className="item-list">
                {items.map((item) => (
                  <button
                    className="item-row"
                    key={item.version.id}
                    onClick={() => {
                      setDetail(null);
                      setSelected(item.version.id);
                      setNote("");
                    }}
                  >
                    <div className="item-meta">
                      {sources.find((s) => s.id === item.source_id)?.name ||
                        item.source_id}
                      <span>{time(item.version.published_at)}</span>
                    </div>
                    <h3>{item.version.title}</h3>
                    <p>{item.version.text.slice(0, 180)}</p>
                    <div className="item-bottom">
                      <span>{item.version.acquisition}</span>
                      <span>查看原文与提取 ↗</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>
        )}
        {tab === "items" && selected && (
          <section>
            <button
              className="back"
              onClick={() => {
                setSelected(null);
                setDetail(null);
              }}
            >
              ← 返回材料
            </button>
            {!detail ? (
              <p>正在读取材料…</p>
            ) : (
              <>
                <div className="detail-heading">
                  <h2>{detail.version.title}</h2>
                  <p>
                    发布 {time(detail.version.published_at)} · 抓取{" "}
                    {time(detail.version.captured_at)} ·{" "}
                    {detail.version.author || "作者未知"}
                  </p>
                  <div className="actions">
                    <a href={detail.item.url} target="_blank" rel="noreferrer">
                      访问原始出处 ↗
                    </a>
                    <a
                      href={`/api/versions/${selected}/snapshot`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      保存快照 ↗
                    </a>
                    <button
                      disabled={
                        busy ||
                        [
                          "pending",
                          "running",
                          "retryable",
                          "budget_wait",
                        ].includes(latest?.status || "")
                      }
                      onClick={() =>
                        void action(
                          () =>
                            api(`/versions/${selected}/normalize`, {
                              force: !!latest,
                            }),
                          "提取任务已排队；Worker 与 Beat 运行时将自动处理",
                        )
                      }
                    >
                      {latest ? "重新提取" : "开始 AI 提取"}
                    </button>
                  </div>
                </div>
                {detail.version.limitations.map((l) => (
                  <div className="banner" key={l}>
                    {l}
                  </div>
                ))}
                <div className="comparison">
                  <article className="raw">
                    <div className="panel-title">原文 · 保存版本</div>
                    {detail.version.paragraphs.map((p) => (
                      <div className="paragraph" id={p.id} key={p.id}>
                        <a href={`#${p.id}`}>{p.id}</a>
                        <p>{p.text}</p>
                      </div>
                    ))}
                  </article>
                  <article className="normalized">
                    <div className="panel-title">结构化提取 · 待人工复核</div>
                    {!latest ? (
                      <p className="muted">
                        尚未提取。点击上方按钮，使用本机 Codex 处理这份材料。
                      </p>
                    ) : (
                      <>
                        <Status value={latest.status} />
                        <small className="run-meta">
                          {latest.prompt_version} · 尝试 {latest.attempts} 次
                        </small>
                        {latest.error && (
                          <div className="banner error">{latest.error}</div>
                        )}
                        {latest.output && (
                          <>
                            <h3>摘要</h3>
                            <p>{latest.output.summary}</p>
                            <h3>原文陈述</h3>
                            {latest.output.claims.map((c, i) => (
                              <div className="claim" key={i}>
                                <small>
                                  {c.kind === "reported_claim"
                                    ? "作者 / 机构主张"
                                    : "待核实事实候选"}
                                </small>
                                <p>{c.text}</p>
                                <blockquote>{c.quote}</blockquote>
                                <div>
                                  {c.paragraph_ids.map((pid) => (
                                    <a key={pid} href={`#${pid}`}>
                                      {pid} ↗{" "}
                                    </a>
                                  ))}
                                </div>
                              </div>
                            ))}
                            <h3>实体与主题</h3>
                            <div className="tags">
                              {latest.output.entities.map((e, i) => (
                                <span key={i}>{e.name}</span>
                              ))}
                              {latest.output.topics.map((t) => (
                                <span key={t}>{t}</span>
                              ))}
                            </div>
                            <h3>未知与限制</h3>
                            {latest.output.uncertainties.length ? (
                              latest.output.uncertainties.map((u, i) => (
                                <p key={i}>{u}</p>
                              ))
                            ) : (
                              <p className="muted">
                                模型未列出额外限制，仍需人工核对。
                              </p>
                            )}
                            <form
                              className="review-form"
                              onSubmit={(e) => {
                                e.preventDefault();
                                review("accepted");
                              }}
                            >
                              <h3>记录提取复核</h3>
                              <p className="muted">
                                此操作只评价提取质量；内容尚未经过发布审核。
                              </p>
                              <label>
                                复核人
                                <input
                                  required
                                  value={reviewer}
                                  onChange={(e) => setReviewer(e.target.value)}
                                  placeholder="你的名字"
                                />
                              </label>
                              <label>
                                核对结果
                                <textarea
                                  required
                                  value={note}
                                  onChange={(e) => setNote(e.target.value)}
                                  placeholder="关键字段是否准确，有哪些缺口或需修正之处？"
                                />
                              </label>
                              <div className="actions">
                                <button
                                  disabled={
                                    busy || !reviewer.trim() || !note.trim()
                                  }
                                >
                                  提取符合原文
                                </button>
                                <button
                                  type="button"
                                  disabled={
                                    busy || !reviewer.trim() || !note.trim()
                                  }
                                  onClick={() => review("needs_correction")}
                                >
                                  需要修正
                                </button>
                              </div>
                            </form>
                          </>
                        )}
                        <details>
                          <summary>处理元数据与原始输出</summary>
                          <pre>
                            {JSON.stringify(latest.attempts_log, null, 2)}
                          </pre>
                          <pre>{JSON.stringify(latest.metadata, null, 2)}</pre>
                          {latest.raw_output && <pre>{latest.raw_output}</pre>}
                        </details>
                      </>
                    )}
                    {!!detail.reviews.length && (
                      <div className="reviews">
                        <h3>人工复核历史</h3>
                        {detail.reviews.map((r) => (
                          <div key={r.id}>
                            <small>
                              {r.reviewer} · {time(r.created_at)} ·{" "}
                              {r.decision === "accepted"
                                ? "符合原文"
                                : "需要修正"}
                            </small>
                            <p>{r.note}</p>
                          </div>
                        ))}
                      </div>
                    )}
                    {detail.runs.length > 1 && (
                      <details>
                        <summary>此前 {detail.runs.length - 1} 次提取</summary>
                        {detail.runs.slice(1).map((r) => (
                          <div key={r.id}>
                            <Status value={r.status} />
                            <span>{time(r.created_at)}</span>
                            <pre>{JSON.stringify(r.output, null, 2)}</pre>
                          </div>
                        ))}
                      </details>
                    )}
                  </article>
                </div>
              </>
            )}
          </section>
        )}
        {tab === "sources" && (
          <section>
            <div className="section-heading">
              <h2>Source Registry</h2>
              <span>登记与实际接通分别统计</span>
            </div>
            <div className="source-grid">
              {sources.map((s) => (
                <article className="source-card" key={s.id}>
                  <div className="section-heading">
                    <span className="role">{s.role}</span>
                    <Status value={s.status} />
                  </div>
                  <h3>
                    <a href={s.node_url} target="_blank" rel="noreferrer">
                      {s.name} ↗
                    </a>
                  </h3>
                  <p>{s.authority}</p>
                  <p className="muted">{s.bias}</p>
                  <div className="source-health">
                    最近成功：
                    {s.last_success_at ? time(s.last_success_at) : "尚未验证"}
                    <br />每 {s.interval_hours} 小时检查
                  </div>
                  <div className="actions">
                    <button
                      disabled={busy || s.status !== "active"}
                      onClick={() =>
                        void action(
                          () =>
                            api(`/sources/${s.id}/collect`, {
                              actor: "local-editor",
                            }),
                          "采集已排队；Worker 与 Beat 运行时将自动处理",
                        )
                      }
                    >
                      采集一次
                    </button>
                    <button
                      disabled={busy}
                      onClick={() =>
                        void action(
                          () =>
                            api(
                              `/sources/${s.id}`,
                              {
                                actor: "local-editor",
                                status:
                                  s.status === "active" ? "paused" : "active",
                              },
                              "PATCH",
                            ),
                          "来源状态已更新",
                        )
                      }
                    >
                      {s.status === "active" ? "暂停" : "启用"}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}
        {tab === "activity" && (
          <section>
            <div className="section-heading">
              <h2>采集记录</h2>
              <span>重试不增加计划任务数</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>来源 / 计划时间</th>
                    <th>状态</th>
                    <th>检查条数</th>
                    <th>本轮未处理</th>
                    <th>新版本</th>
                    <th>尝试</th>
                    <th>说明</th>
                  </tr>
                </thead>
                <tbody>
                  {checks.map((c) => (
                    <tr key={c.id}>
                      <td>
                        {c.source_id}
                        <small>
                          {time(c.scheduled_at)} ·{" "}
                          {c.slot.startsWith("manual:") ? "手动" : "计划"}
                        </small>
                      </td>
                      <td>
                        <Status value={c.status} />
                      </td>
                      <td>{c.item_count}</td>
                      <td>{c.deferred_count ?? 0}</td>
                      <td>{c.new_versions}</td>
                      <td>{c.attempts}</td>
                      <td className="error-cell">
                        {c.error || "—"}
                        {!!c.attempts_log?.length && (
                          <details>
                            <summary>重试历史</summary>
                            <pre>{JSON.stringify(c.attempts_log, null, 2)}</pre>
                          </details>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!checks.length && <p className="empty">还没有采集记录。</p>}
            </div>
            <div className="section-heading">
              <h2>AI 处理记录</h2>
              <span>费用无法获取时记为未知</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>任务</th>
                    <th>状态</th>
                    <th>模型配置</th>
                    <th>耗时</th>
                    <th>费用</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <button
                          onClick={() => {
                            setTab("items");
                            setSelected(r.version_id);
                            setDetail(null);
                          }}
                        >
                          {r.id.slice(0, 8)} ↗
                        </button>
                        <small>{time(r.created_at)}</small>
                      </td>
                      <td>
                        <Status value={r.status} />
                      </td>
                      <td>{r.model}</td>
                      <td>
                        {r.metadata.duration_seconds
                          ? `${r.metadata.duration_seconds}s`
                          : "—"}
                      </td>
                      <td>{r.metadata.cost ?? "未知"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
        <footer>
          Less noise. More signal.<span>原始材料 → 结构化提取 → 人工判断</span>
        </footer>
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
