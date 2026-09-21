import { useEffect, useState } from "react";
import { ReadingFeedback } from "./ReadingFeedback";
import { EditorForm, request } from "./editorialForms";
import type { S } from "./editorialForms";

const status: Record<string, string> = {
  draft: "草稿",
  in_review: "审核中",
  approved: "已批准",
  published: "已内部发布",
  needs_review: "需重新审核",
  withdrawn: "已撤回",
};
type Content = S["BriefContent"];
type Source = {
  claim_id: string;
  claim: string;
  kind: string;
  evidence_id: string;
  version_id: string;
  paragraph_ids: string[];
  quote: string;
  direction: string;
  limitations: string;
  source_root: string;
  url: string;
};
type Today = {
  day: string;
  recorded: boolean;
  note: string;
  readable_count: number;
  entries: {
    brief_id: string;
    revision: number;
    status: string;
    content: Content | null;
    sources: Source[];
  }[];
};

export function BriefWorkspace() {
  const [editingOpen, setEditingOpen] = useState(false);
  const [actor, setActor] = useState("");
  const [briefs, setBriefs] = useState<S["BriefView"][]>([]);
  const [events, setEvents] = useState<S["EventView"][]>([]);
  const [eventOffset, setEventOffset] = useState(0);
  const [eventTotal, setEventTotal] = useState(0);
  const [event, setEvent] = useState<S["EventDetail"] | null>(null);
  const [detail, setDetail] = useState<S["BriefDetailView"] | null>(null);
  const [today, setToday] = useState<Today | null>(null);
  const [day, setDay] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [checked, setChecked] = useState(false);
  async function refresh() {
    const [list, edition] = await Promise.all([
      request<S["BriefView"][]>("/briefs"),
      request<Today>(`/today${day ? `?day=${day}` : ""}`),
    ]);
    setBriefs(list);
    setToday(edition);
  }
  async function act(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    let active = true;
    Promise.all([
      request<S["BriefView"][]>("/briefs"),
      request<Today>(`/today${day ? `?day=${day}` : ""}`),
    ])
      .then(([b, t]) => {
        if (active) {
          setBriefs(b);
          setToday(t);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [day]);
  useEffect(() => {
    let active = true;
    request<S["InboxView"]>(
      `/editorial/events?decision=selected&offset=${eventOffset}`,
    )
      .then((r) => {
        if (active) {
          setEvents(r.events);
          setEventTotal(r.total);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [eventOffset]);
  async function openBrief(id: string) {
    const next = await request<S["BriefDetailView"]>(`/briefs/${id}`);
    const original = await request<S["EventDetail"]>(
      `/editorial/events/${next.brief.event_id}`,
    );
    setEditingOpen(true);
    setDetail(next);
    setEvent(original);
    setChecked(false);
  }
  return (
    <section className="validation-desk">
      <h2>Brief 与 Today</h2>
      <p className="muted">
        内部阅读，每天最多 5
        条。事实逐条关联已核验证据，观点单独表达。修改后重新审核，证据变化暂停展示。
      </p>
      {error && (
        <p className="banner error" role="alert">
          {error}
        </p>
      )}
      <label>
        编辑姓名
        <input
          aria-label="Brief 编辑姓名"
          value={actor}
          maxLength={80}
          onChange={(e) => setActor(e.target.value)}
        />
      </label>
      <details
        className="work-panel"
        open={editingOpen}
        onToggle={(e) => setEditingOpen(e.currentTarget.open)}
      >
        <summary>编辑 Brief</summary>
        <label>
          已保存 Brief
          <select
            disabled={busy}
            value={detail?.brief.id ?? ""}
            onChange={(e) => {
              if (e.target.value) void act(() => openBrief(e.target.value));
            }}
          >
            <option value="">请选择</option>
            {briefs.map((b) => (
              <option key={b.id} value={b.id}>
                {b.id.slice(0, 8)} · {status[b.status]} · 版本 {b.revision}
              </option>
            ))}
          </select>
        </label>
        <label>
          从入选事件起草
          <select
            disabled={busy}
            value={event && !detail ? event.event.id : ""}
            onChange={(e) => {
              if (e.target.value)
                void act(async () => {
                  const original = await request<S["EventDetail"]>(
                    `/editorial/events/${e.target.value}`,
                  );
                  setEvent(original);
                  setDetail(null);
                  setChecked(false);
                });
            }}
          >
            <option value="">选择已通过两道门的事件</option>
            {events.map((e) => (
              <option value={e.id} key={e.id}>
                {e.title}
              </option>
            ))}
          </select>
        </label>
        <div className="validation-actions">
          <button
            disabled={busy || eventOffset === 0}
            onClick={() => setEventOffset(eventOffset - 50)}
          >
            上一页事件
          </button>
          <span>{eventTotal} 个入选事件</span>
          <button
            disabled={busy || eventOffset + 50 >= eventTotal}
            onClick={() => setEventOffset(eventOffset + 50)}
          >
            下一页事件
          </button>
        </div>
        {event && (
          <>
            <h3>{event.event.title}</h3>
            {detail && (
              <p>
                当前状态：{status[detail.brief.status]} · 版本{" "}
                {detail.brief.revision}
                {!detail.current_eligible && " · 事件或证据需要先重新审核"}
              </p>
            )}
            <DraftEditor
              key={`${event.event.id}:${event.event.revision}:${detail?.brief.revision ?? 0}`}
              event={event}
              initial={detail?.versions[0]?.content as Content | undefined}
              disabled={
                busy || !actor.trim() || event.event.decision !== "selected"
              }
              submit={(values) =>
                act(async () => {
                  const b = await request<S["BriefView"]>("/briefs", {
                    ...values,
                    actor,
                    event_id: event.event.id,
                    event_revision: event.event.revision,
                    expected_revision: detail?.brief.revision ?? 0,
                  });
                  await openBrief(b.id);
                  await refresh();
                })
              }
            />
            {detail && (
              <>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => setChecked(e.target.checked)}
                  />
                  我已核对原文、事实与解释边界及新增价值
                </label>
                <EditorForm
                  key={`${detail.brief.id}:${detail.brief.revision}:${detail.brief.status}`}
                  fields={[
                    {
                      key: "action",
                      label: "Brief 操作",
                      options: [
                        ["submit", "提交审核"],
                        ["approve", "人工批准当前版本"],
                        ["publish", "内部发布到今天"],
                        ["return_to_draft", "退回草稿"],
                        ["withdraw", "撤回内容"],
                      ],
                    },
                    { key: "reason", label: "审核或发布依据", multiline: true },
                  ]}
                  label="执行 Brief 操作"
                  disabled={busy || !actor.trim()}
                  submit={(v) =>
                    act(async () => {
                      await request(`/briefs/${detail.brief.id}/actions`, {
                        ...v,
                        actor,
                        revision: detail.brief.revision,
                        original_checked: checked,
                      });
                      await openBrief(detail.brief.id);
                      await refresh();
                    })
                  }
                />
                <ReadingFeedback
                  detail={detail}
                  actor={actor}
                  disabled={busy || !actor.trim()}
                />
                <details>
                  <summary>版本与审核历史</summary>
                  {detail.reviews.map((r) => (
                    <p key={r.id}>
                      {r.actor} ·{" "}
                      {new Date(r.created_at).toLocaleString("zh-CN")} · 版本{" "}
                      {r.revision} · {r.action}：{r.reason}
                    </p>
                  ))}
                  {detail.versions.map((v) => (
                    <details key={v.id}>
                      <summary>
                        版本 {v.revision} · {v.actor} · {v.reason}
                      </summary>
                      <BriefArticle
                        content={v.content as Content}
                        sources={v.sources as Source[]}
                      />
                    </details>
                  ))}
                </details>
              </>
            )}
          </>
        )}
      </details>
      <div className="section-heading">
        <h2>Today</h2>
        <input
          aria-label="阅读日期"
          type="date"
          value={day}
          onChange={(e) => setDay(e.target.value)}
        />
      </div>
      {today && (
        <>
          <p>
            {today.day} · {today.readable_count} 条可读内容
          </p>
          {!today.recorded && <p className="muted">当天尚无编辑记录。</p>}
          {today.note && <p>{today.note}</p>}
          {today.entries.map((entry) => (
            <article className="work-panel" key={entry.brief_id}>
              {entry.content ? (
                <BriefArticle content={entry.content} sources={entry.sources} />
              ) : (
                <p>
                  {status[entry.status]} · 原版本 {entry.revision}{" "}
                  暂不展示，请查看更正记录。
                </p>
              )}
              <button
                disabled={busy}
                onClick={() => void act(() => openBrief(entry.brief_id))}
              >
                查看版本与更正
              </button>
            </article>
          ))}
          {!today.entries.length && <p>今天没有已发布内容，不为凑数填充。</p>}
        </>
      )}
      <details className="work-panel">
        <summary>记录今天的编辑情况</summary>
        <p className="muted">
          记录低产、证据缺口或没有合格内容的原因，只记录当前日期。
        </p>
        <EditorForm
          fields={[{ key: "note", label: "今日编辑记录", multiline: true }]}
          label="保存今日记录"
          disabled={busy || !actor.trim()}
          submit={(v) =>
            act(async () => {
              await request("/today/note", { ...v, actor });
              await refresh();
            })
          }
        />
      </details>
    </section>
  );
}

function DraftEditor({
  event,
  initial,
  disabled,
  submit,
}: {
  event: S["EventDetail"];
  initial?: Content;
  disabled: boolean;
  submit: (v: Record<string, unknown>) => Promise<void>;
}) {
  const [chosen, setChosen] = useState<string[]>(
    initial?.facts.flatMap((f) => f.evidence_ids) ?? [],
  );
  return (
    <div>
      <p>
        选择稿件陈述的已核验证据。必须涵盖全部关键陈述，每条至少有一条支持证据。
      </p>
      {event.claims.map((c) => (
        <fieldset className="paragraph-picker" key={c.id}>
          <legend>
            {c.text} · {c.critical ? "关键" : "辅助"}
          </legend>
          {event.evidence
            .filter((e) => e.claim_id === c.id && e.status === "verified")
            .map((e) => (
              <label className="checkbox-label" key={e.id}>
                <input
                  type="checkbox"
                  checked={chosen.includes(e.id)}
                  onChange={(v) =>
                    setChosen((ids) =>
                      v.target.checked
                        ? [...ids, e.id]
                        : ids.filter((id) => id !== e.id),
                    )
                  }
                />
                <span>
                  {e.direction === "supporting"
                    ? "支持"
                    : e.direction === "counter"
                      ? "反面"
                      : "背景"}
                  ：{e.quote} · {e.limitations}
                </span>
              </label>
            ))}
        </fieldset>
      ))}
      <EditorForm
        fields={[
          {
            key: "title",
            label: "Brief 标题",
            initial: initial?.title ?? event.event.title,
          },
          {
            key: "why_it_matters",
            label: "Why it matters · 对谁有何价值",
            initial: initial?.why_it_matters,
            multiline: true,
          },
          {
            key: "what_changed",
            label: "What changed · 相比之前的变化",
            initial: initial?.what_changed,
            multiline: true,
          },
          {
            key: "our_take",
            label: "Our take · 解释与判断",
            initial: initial?.our_take,
            multiline: true,
          },
          {
            key: "try_it",
            label: "Try it · 适用者与尝试方式（可空）",
            initial: initial?.try_it,
            multiline: true,
            optional: true,
          },
          { key: "reason", label: "起草或更正依据", multiline: true },
        ]}
        label="保存 Brief 草稿"
        disabled={disabled}
        submit={(v) => {
          const { reason, ...content } = v;
          return submit({
            reason,
            content: {
              ...content,
              facts: event.claims
                .map((c) => ({
                  claim_id: c.id,
                  evidence_ids: event.evidence
                    .filter((e) => e.claim_id === c.id && chosen.includes(e.id))
                    .map((e) => e.id),
                }))
                .filter((f) => f.evidence_ids.length),
            },
          });
        }}
      />
    </div>
  );
}

function BriefArticle({
  content,
  sources,
}: {
  content: Content;
  sources: Source[];
}) {
  const claims = [...new Map(sources.map((s) => [s.claim_id, s])).values()];
  return (
    <>
      <h3>{content.title}</h3>
      <h4>What happened</h4>
      {claims.map((c) => (
        <p key={c.claim_id}>
          <span className="muted">
            {c.kind === "reported_claim"
              ? "有归属的主张"
              : c.kind === "interpretation"
                ? "解释 / 推断"
                : "已核查陈述"}{" "}
            ·{" "}
          </span>
          {c.claim}
        </p>
      ))}
      <h4>Why it matters</h4>
      <p>{content.why_it_matters}</p>
      <h4>What changed</h4>
      <p>{content.what_changed}</p>
      <h4>Our take</h4>
      <p>{content.our_take}</p>
      {content.try_it && (
        <>
          <h4>Try it</h4>
          <p>{content.try_it}</p>
        </>
      )}
      <details>
        <summary>Sources · 原文与证据</summary>
        {sources.map((s) => (
          <div className="session-card" key={s.evidence_id}>
            <blockquote>{s.quote}</blockquote>
            <p>{s.limitations}</p>
            <a href={s.url} target="_blank" rel="noreferrer">
              原始出处 ↗
            </a>
            {" · "}
            <a
              href={`/api/versions/${s.version_id}/snapshot`}
              target="_blank"
              rel="noreferrer"
            >
              保存版本 ↗
            </a>
            <p className="muted">
              段落：{s.paragraph_ids.join(", ")} · 来源根：{s.source_root}
            </p>
          </div>
        ))}
      </details>
    </>
  );
}
