import { useEffect, useState } from "react";
import { ValueAudit } from "./ValueAudit";
import { request } from "./editorialForms";
import type { S } from "./editorialForms";
import type { Item } from "./types";
const stages: Record<string, string> = {
  event: "原文 → 事件草稿",
  value: "Important / Useful 初筛",
  pair: "语义与引用关系聚类建议",
  brief: "Brief 写作草稿",
};
const states: Record<string, string> = {
  pending: "等待执行",
  running: "处理中",
  retryable: "等待重试",
  budget_wait: "等待次日调用预算",
  blocked: "额度或登录暂停",
  failed: "失败",
  succeeded: "处理完成",
};
type Ranking = {
  rows: {
    event: S["EventView"];
    run_id: string;
    proposal: {
      important: number;
      useful: number;
      important_reason: string;
      useful_reason: string;
      uncertain: boolean;
      limitations: string[];
    };
    selection: string;
  }[];
  unassessed_events: number;
  method: string;
  limitations: string;
};
export function AssistWorkspace({ items }: { items: Item[] }) {
  const [actor, setActor] = useState("");
  const [stage, setStage] = useState("event");
  const [version, setVersion] = useState("");
  const [eventIds, setEventIds] = useState<string[]>([]);
  const [events, setEvents] = useState<S["EventView"][]>([]);
  const [eventOffset, setEventOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [runs, setRuns] = useState<S["AssistView"][]>([]);
  const [rank, setRank] = useState<Ranking | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  async function refresh() {
    const [r, c] = await Promise.all([
      request<S["AssistView"][]>(`/assist?offset=${offset}`),
      request<Ranking>("/assist/candidates"),
    ]);
    setRuns(r);
    setRank(c);
  }
  useEffect(() => {
    let active = true;
    const update = () =>
      Promise.all([
        request<S["AssistView"][]>(`/assist?offset=${offset}`),
        request<Ranking>("/assist/candidates"),
      ])
        .then(([r, c]) => {
          if (active) {
            setRuns(r);
            setRank(c);
          }
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    void update();
    const timer = setInterval(update, 8000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [offset]);
  useEffect(() => {
    let active = true;
    request<S["InboxView"]>(`/editorial/events?offset=${eventOffset}`)
      .then((v) => {
        if (active) {
          setEvents(v.events);
          setTotal(v.total);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [eventOffset]);
  async function act(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const disabled = busy || !actor.trim();
  return (
    <section className="validation-desk">
      <h2>机器辅助与候选排序</h2>
      <p className="muted">
        机器结果与人工判断分开保存。共享每日 AI
        调用预算；缺证据不自动等于低价值，所有证据和发布仍需明确审核。
      </p>
      {error && (
        <p role="alert" className="banner error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="banner">
          {notice}
        </p>
      )}
      <label>
        操作人
        <input
          value={actor}
          maxLength={80}
          onChange={(e) => setActor(e.target.value)}
        />
      </label>
      <div className="work-panel">
        <label>
          辅助任务
          <select
            value={stage}
            onChange={(e) => {
              setStage(e.target.value);
              setEventIds([]);
            }}
          >
            {Object.entries(stages).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        {stage === "event" ? (
          <label>
            选择原始版本（最近 100 份）
            <select
              value={version}
              onChange={(e) => setVersion(e.target.value)}
            >
              <option value="">请选择原文</option>
              {items.map((i) => (
                <option key={i.version.id} value={i.version.id}>
                  {i.version.title}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <>
            <p>
              选择 {stage === "pair" ? 2 : 1} 个事件，已选 {eventIds.length} 个
            </p>
            <fieldset className="paragraph-picker">
              <legend>任务事件</legend>
              {events.map((e) => (
                <label className="checkbox-label" key={e.id}>
                  <input
                    type="checkbox"
                    checked={eventIds.includes(e.id)}
                    disabled={
                      !eventIds.includes(e.id) &&
                      eventIds.length >= (stage === "pair" ? 2 : 1)
                    }
                    onChange={(v) =>
                      setEventIds((ids) =>
                        v.target.checked
                          ? [...ids, e.id]
                          : ids.filter((id) => id !== e.id),
                      )
                    }
                  />
                  {e.title}
                </label>
              ))}
            </fieldset>
            <div className="validation-actions">
              <button
                disabled={!eventOffset}
                onClick={() => setEventOffset(eventOffset - 50)}
              >
                上一页事件
              </button>
              <button
                disabled={eventOffset + 50 >= total}
                onClick={() => setEventOffset(eventOffset + 50)}
              >
                下一页事件
              </button>
              <button onClick={() => setEventIds([])}>清空选择</button>
            </div>
          </>
        )}
        <button
          disabled={
            disabled ||
            (stage === "event"
              ? !version
              : eventIds.length !== (stage === "pair" ? 2 : 1))
          }
          onClick={() =>
            void act(async () => {
              await request("/assist", {
                actor,
                stage,
                version_id: stage === "event" ? version : null,
                event_ids: eventIds,
              });
              setNotice("任务已入队，相同输入与提示版本会复用已有任务");
            })
          }
        >
          加入处理队列
        </button>
      </div>
      {rank && (
        <details className="work-panel" open>
          <summary>
            候选、排除与待判断 · {rank.rows.length} 个已评估事件
          </summary>
          <p>{rank.method}</p>
          <p className="muted">
            {rank.limitations} · 尚未评估 {rank.unassessed_events} 个事件
          </p>
          {rank.rows.map((r) => (
            <div className="session-card" key={r.run_id}>
              <strong>{r.event.title}</strong>
              <p>
                {
                  (
                    {
                      candidate: "机器候选",
                      excluded: "机器排除，保留抽查",
                      pending: "机器无法明确判断",
                    } as Record<string, string>
                  )[r.selection]
                }{" "}
                · Important {r.proposal.important}/3 · Useful{" "}
                {r.proposal.useful}/3
              </p>
              <p>重要性：{r.proposal.important_reason}</p>
              <p>实用性：{r.proposal.useful_reason}</p>
              {r.proposal.limitations.map((l, i) => (
                <p className="muted" key={i}>
                  {l}
                </p>
              ))}
            </div>
          ))}
        </details>
      )}
      <ValueAudit actor={actor} />
      <h3>辅助任务记录</h3>
      <div className="validation-actions">
        <button
          disabled={!offset || busy}
          onClick={() => setOffset(offset - 50)}
        >
          上一页任务
        </button>
        <button
          disabled={runs.length < 50 || busy}
          onClick={() => setOffset(offset + 50)}
        >
          下一页任务
        </button>
      </div>
      {runs.map((run) => (
        <details className="work-panel" key={run.id}>
          <summary>
            {stages[run.stage]} · {states[run.status]} ·{" "}
            {new Date(run.created_at).toLocaleString("zh-CN")}
          </summary>
          <p className="muted">
            {run.model} · {run.prompt_version} · 尝试 {run.attempts} 次
          </p>
          {run.error && <p>{run.error}</p>}
          {run.output && <AssistResult run={run} />}
          <div className="validation-actions">
            {(run.status === "failed" || run.status === "blocked") && (
              <button
                disabled={disabled}
                onClick={() =>
                  void act(async () => {
                    await request(`/assist/${run.id}/retry`, { actor });
                    setNotice("已请求重试；全局额度暂停仍按现有状态处理");
                  })
                }
              >
                重试任务
              </button>
            )}
            {run.stage === "event" &&
              run.status === "succeeded" &&
              !run.output?.uncertain && (
                <button
                  disabled={disabled}
                  onClick={() =>
                    void act(async () => {
                      const e = await request<S["EventView"]>(
                        `/assist/${run.id}/event`,
                        { actor },
                      );
                      setNotice(
                        `已保存待核验事件：${e.title}。请在编辑收件箱中审核。`,
                      );
                    })
                  }
                >
                  {run.applied_event_id
                    ? "查看已采用事件信息"
                    : "采用为待核验事件"}
                </button>
              )}
            {run.stage === "brief" && run.status === "succeeded" && (
              <button
                disabled={disabled}
                onClick={() =>
                  void act(async () => {
                    const original = (
                      run.input.events as { id: string; revision: number }[]
                    )[0];
                    await request("/briefs", {
                      actor,
                      event_id: original.id,
                      event_revision: original.revision,
                      expected_revision: run.input.brief_revision,
                      content: run.output,
                      reason: `采用机器写作草稿 ${run.id}，尚未批准`,
                    });
                    setNotice(
                      "已保存为 Brief 草稿，请在 Brief 与 Today 中核对和审核。",
                    );
                  })
                }
              >
                采用为未批准 Brief 草稿
              </button>
            )}
          </div>
        </details>
      ))}
    </section>
  );
}
function AssistResult({ run }: { run: S["AssistView"] }) {
  const output = run.output!;
  const fields: Record<string, string> = {
    important_reason: "重要性理由",
    useful_reason: "实用性理由",
    reason: "聚类判断依据",
    verdict: "同事件判断",
    title: "标题",
    why_it_matters: "Why it matters",
    what_changed: "What changed",
    our_take: "Our take",
    try_it: "Try it",
  };
  return (
    <div>
      <p className="muted">
        机器草稿或建议，未经人工批准。语义聚类只使用所提供的原文与已登记来源关系，不代表完整引用链验证。
      </p>
      {Object.entries(fields)
        .filter(([k]) => typeof output[k] === "string")
        .map(([k, label]) => (
          <p key={k}>
            <strong>{label}：</strong>
            {String(output[k])}
          </p>
        ))}
      {Boolean(output.event) && (
        <div>
          {Object.entries(output.event as Record<string, unknown>).map(
            ([k, v]) => (
              <p key={k}>
                {(
                  {
                    title: "事件",
                    subject: "主体",
                    action: "动作",
                    object: "对象",
                    scope: "范围",
                    event_version: "版本",
                    happened_at: "时间",
                  } as Record<string, string>
                )[k] ?? k}
                ：{v == null ? "未知" : String(v)}
              </p>
            ),
          )}
        </div>
      )}
      {[
        ...((output.claims ?? []) as {
          text?: string;
          quote?: string;
          paragraph_ids?: string[];
        }[]),
        ...((output.citations ?? []) as {
          text?: string;
          quote?: string;
          paragraph_ids?: string[];
          version_id?: string;
        }[]),
      ].map((c, i) => (
        <div className="session-card" key={i}>
          {c.text && <p>{c.text}</p>}
          {c.quote && <blockquote>{c.quote}</blockquote>}
          <p className="muted">段落：{c.paragraph_ids?.join(", ")}</p>
        </div>
      ))}
      {((output.conflicts ?? []) as string[]).map((v, i) => (
        <p className="cluster-conflicts" key={i}>
          {v}
        </p>
      ))}
      {((output.limitations ?? []) as string[]).map((v, i) => (
        <p className="muted" key={i}>
          {v}
        </p>
      ))}
    </div>
  );
}
