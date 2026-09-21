import { useCallback, useEffect, useState } from "react";
import {
  EditorForm,
  request,
  states,
  reason,
  skeleton,
} from "./editorialForms";
import type { S, EventDetail } from "./editorialForms";
import { EventClusterTools, ClusterSuggestions } from "./ClusterTools";
import { ClusterAudit } from "./ClusterAudit";
import type { Detail, Item } from "./types";

export function EditorialInbox({ items }: { items: Item[] }) {
  const [actor, setActor] = useState("");
  const [filter, setFilter] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [offset, setOffset] = useState(0);
  const [inbox, setInbox] = useState<S["InboxView"] | null>(null);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<EventDetail | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  function openEvent(id: string) {
    setSelected(id);
    setDetail(null);
  }
  const load = useCallback(async () => {
    const [list, current] = await Promise.all([
      request<S["InboxView"]>(
        `/editorial/events?offset=${offset}&include_archived=${includeArchived}${filter ? `&decision=${filter}` : ""}`,
      ),
      selected ? request<EventDetail>(`/editorial/events/${selected}`) : null,
    ]);
    return { list, current };
  }, [selected, filter, offset, includeArchived]);
  useEffect(() => {
    let active = true;
    load()
      .then(({ list, current }) => {
        if (active) {
          setInbox(list);
          setDetail(current);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [load]);
  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
      const { list, current } = await load();
      setInbox(list);
      setDetail(current);
      setNotice("已保存，操作与原有记录均可追溯");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="validation-desk editorial-inbox">
      {error && (
        <div className="banner error" role="alert">
          {error}
          <button onClick={() => setError("")}>关闭</button>
        </div>
      )}
      {notice && (
        <div className="banner" role="status">
          {notice}
        </div>
      )}
      <div className="section-heading">
        <h2>Editorial Inbox</h2>
        <span>事件 → 价值 → 证据 → 编辑决定</span>
      </div>
      <p className="muted">
        Important 或 Useful
        任一成立可通过价值门。证据质量单独核验；入选事件还需要后续 Brief
        审核，当前不会直接发布。
      </p>
      <div className="validation-identity">
        <label>
          编辑姓名
          <input
            value={actor}
            maxLength={80}
            onChange={(e) => setActor(e.target.value)}
            placeholder="用于判断与更正记录"
          />
        </label>
      </div>
      {selected ? (
        <>
          <button
            className="back"
            onClick={() => {
              setSelected("");
              setDetail(null);
            }}
          >
            ← 返回事件列表
          </button>
          {detail && (
            <EventEditor
              key={`${detail.event.id}:${detail.event.revision}`}
              detail={detail}
              items={items}
              actor={actor}
              busy={busy}
              act={act}
              onOpen={openEvent}
            />
          )}
        </>
      ) : (
        <>
          <ClusterSuggestions onOpen={openEvent} />
          <ClusterAudit actor={actor} />
          <details className="work-panel">
            <summary>新建事件骨架</summary>
            <EditorForm
              fields={skeleton}
              label="创建事件"
              disabled={busy || !actor.trim()}
              submit={async (values) => {
                let createdId = "";
                await act(async () => {
                  const created = await request<S["EventView"]>(
                    "/editorial/events",
                    {
                      ...values,
                      actor,
                      event_version: values.event_version || null,
                    },
                  );
                  createdId = created.id;
                });
                if (createdId) setSelected(createdId);
              }}
            />
          </details>
          <label className="batch-selector">
            编辑状态
            <select
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">全部事件</option>
              {[
                "pending",
                "selected",
                "deferred",
                "rejected",
                "evidence_only",
                "observe",
              ].map((s) => (
                <option key={s} value={s}>
                  {states[s]}
                </option>
              ))}
            </select>
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(e) => {
                setIncludeArchived(e.target.checked);
                setOffset(0);
              }}
            />
            显示已合并和归档的历史事件
          </label>
          {!inbox?.events.length ? (
            <div className="empty">
              <h3>先写清楚：谁，做了什么</h3>
              <p>建立事件并关联原文，然后分别记录价值理由与证据缺口。</p>
            </div>
          ) : (
            <div className="item-list inbox-events">
              {inbox.events.map((event) => (
                <button
                  className="item-row"
                  key={event.id}
                  onClick={() => {
                    setSelected(event.id);
                    setDetail(null);
                  }}
                >
                  <div className="item-meta">
                    <span>
                      {states[event.decision]} · 修订 {event.revision}
                    </span>
                    <span>
                      {new Date(event.created_at).toLocaleDateString("zh-CN")}
                    </span>
                  </div>
                  <h3>{event.title}</h3>
                  {event.lifecycle && event.lifecycle !== "active" && (
                    <p className="muted">
                      {event.lifecycle === "merged"
                        ? "已合并，保留原事件去向"
                        : "已归档，保留恢复记录"}
                    </p>
                  )}
                  <p className="muted">
                    {event.subject} · {event.action} · {event.object}
                  </p>
                  <div className="tags">
                    <span>价值：{states[event.value_status]}</span>
                    <span>质量：{states[event.quality_status]}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
          <div className="validation-actions">
            <button
              disabled={offset === 0 || busy}
              onClick={() => setOffset(Math.max(0, offset - 50))}
            >
              上一页
            </button>
            <span className="muted">共 {inbox?.total ?? 0} 个事件</span>
            <button
              disabled={busy || !inbox || offset + 50 >= inbox.total}
              onClick={() => setOffset(offset + 50)}
            >
              下一页
            </button>
          </div>
        </>
      )}
    </section>
  );
}

type EditorProps = {
  detail: EventDetail;
  items: Item[];
  actor: string;
  busy: boolean;
  act: (fn: () => Promise<unknown>) => Promise<void>;
  onOpen: (id: string) => void;
};
function EventEditor({ detail, items, actor, busy, act, onOpen }: EditorProps) {
  const { event } = detail;
  const disabled =
    busy || !actor.trim() || (event.lifecycle ?? "active") !== "active";
  const base = `/editorial/events/${event.id}`;
  function post(
    path: string,
    values: Record<string, unknown>,
    method = "POST",
  ) {
    return act(() =>
      request(
        base + path,
        { actor, revision: event.revision, ...values },
        method,
      ),
    );
  }
  if ((event.lifecycle ?? "active") !== "active")
    return (
      <div className="event-editor">
        <h2>{event.title}</h2>
        <p className="muted">
          此事件{event.lifecycle === "merged" ? "已合并" : "已归档"}
          ，旧记录保留供追溯。
        </p>
        {event.redirected_to && (
          <button onClick={() => onOpen(event.redirected_to!)}>
            打开映射到的事件
          </button>
        )}
        <EventClusterTools
          detail={detail}
          actor={actor}
          busy={busy}
          act={act}
          onOpen={onOpen}
        />
        <details className="work-panel">
          <summary>原事件审核与更正记录</summary>
          {detail.reviews.map((r) => (
            <div className="session-card" key={r.id}>
              <p>
                {r.actor} · 修订 {r.revision} ·{" "}
                {new Date(r.created_at).toLocaleString("zh-CN")}
              </p>
              <pre>
                {JSON.stringify(
                  { gate: r.gate, status: r.status, detail: r.detail },
                  null,
                  2,
                )}
              </pre>
            </div>
          ))}
          {detail.history.map((h) => (
            <div className="session-card" key={h.id}>
              <p>
                {h.actor} · {new Date(h.created_at).toLocaleString("zh-CN")}
              </p>
              <pre>
                {JSON.stringify(
                  { action: h.action, detail: h.detail },
                  null,
                  2,
                )}
              </pre>
            </div>
          ))}
        </details>
      </div>
    );
  return (
    <div className="event-editor">
      <h2>{event.title}</h2>
      <div className="tags">
        <span>价值：{states[event.value_status]}</span>
        <span>质量：{states[event.quality_status]}</span>
        <span>决定：{states[event.decision]}</span>
      </div>
      <p>
        {event.subject} · {event.action} · {event.object}
      </p>
      <p className="muted">
        {event.scope} · 版本：{event.event_version || "未知"} · 发生时间：
        {event.happened_at
          ? new Date(event.happened_at).toLocaleString("zh-CN")
          : "未知"}
      </p>
      <EventClusterTools
        detail={detail}
        actor={actor}
        busy={busy}
        act={act}
        onOpen={onOpen}
      />
      <details className="work-panel">
        <summary>修正事件骨架</summary>
        <EditorForm
          fields={[
            ...skeleton.map((f) => ({
              ...f,
              initial: String(event[f.key as keyof typeof event] ?? ""),
            })),
            reason,
          ]}
          label="保存事件修正"
          disabled={disabled}
          submit={(v) =>
            post(
              "",
              {
                ...v,
                event_version: v.event_version || null,
                happened_at: event.happened_at,
              },
              "PATCH",
            )
          }
        />
      </details>
      <details className="work-panel">
        <summary>
          原始材料与关联 · {detail.members.filter((m) => m.active).length} 份
        </summary>
        {detail.members.map((m) => (
          <div className="session-card" key={m.id}>
            <strong>{m.title}</strong>
            <p className="muted">
              {m.source_name} · {m.active ? "已关联" : "已取消关联，历史保留"}
            </p>
            <div className="validation-actions">
              <a href={m.url} target="_blank" rel="noreferrer">
                原始页面 ↗
              </a>
              <a
                href={`/api/versions/${m.version_id}/snapshot`}
                target="_blank"
                rel="noreferrer"
              >
                保存快照 ↗
              </a>
            </div>
            <details>
              <summary>关联段落</summary>
              {m.paragraphs
                .filter((p) => m.paragraph_ids.includes(String(p.id)))
                .map((p) => (
                  <div className="paragraph" key={String(p.id)}>
                    <small>{String(p.id)}</small>
                    <p>{String(p.text)}</p>
                  </div>
                ))}
            </details>
            <EditorForm
              fields={[reason]}
              label={m.active ? "取消这份关联" : "恢复这份关联"}
              disabled={disabled}
              submit={(v) =>
                m.active
                  ? post(`/members/${m.id}/unlink`, v)
                  : post("/members", {
                      ...v,
                      version_id: m.version_id,
                      paragraph_ids: m.paragraph_ids,
                    })
              }
            />
          </div>
        ))}
        <MemberForm
          items={items}
          disabled={disabled}
          submit={(v) => post("/members", v)}
        />
      </details>
      <details className="work-panel" open>
        <summary>关键陈述与证据 · {detail.claims.length} 条陈述</summary>
        {detail.claims.map((c) => (
          <div className="session-card" key={c.id}>
            <strong>{c.text}</strong>
            <p className="muted">
              {states[c.kind]} ·{" "}
              {c.critical ? "影响标题或结论的关键陈述" : "辅助陈述"}
            </p>
            <details>
              <summary>修正这条陈述</summary>
              <EditorForm
                fields={[
                  {
                    key: "text",
                    label: "修正后的陈述",
                    multiline: true,
                    initial: c.text,
                  },
                  {
                    key: "kind",
                    label: "修正后的陈述类型",
                    initial: c.kind,
                    options: [
                      ["reported_claim", "有归属的主张"],
                      ["fact_candidate", "待核验事实"],
                      ["interpretation", "解释 / 推断"],
                    ],
                  },
                  {
                    key: "critical",
                    label: "是否影响标题或结论",
                    initial: String(c.critical),
                    options: [
                      ["true", "关键陈述"],
                      ["false", "辅助陈述"],
                    ],
                  },
                  reason,
                ]}
                label="保存陈述修正"
                disabled={disabled}
                submit={(v) =>
                  post(
                    `/claims/${c.id}`,
                    { ...v, critical: v.critical === "true" },
                    "PATCH",
                  )
                }
              />
            </details>
            {detail.evidence
              .filter((e) => e.claim_id === c.id)
              .map((e) => (
                <EvidenceCard
                  key={e.id}
                  evidence={e}
                  member={detail.members.find(
                    (m) => m.version_id === e.version_id,
                  )}
                  disabled={disabled}
                  submit={(v) => post(`/evidence/${e.id}/review`, v)}
                />
              ))}
            {!detail.evidence.some((e) => e.claim_id === c.id) && (
              <p className="muted">证据缺口：尚未添加可定位材料</p>
            )}
          </div>
        ))}
        <details>
          <summary>添加关键陈述</summary>
          <EditorForm
            fields={[
              { key: "text", label: "需要核实的陈述", multiline: true },
              {
                key: "kind",
                label: "陈述类型",
                options: [
                  ["reported_claim", "有归属的主张"],
                  ["fact_candidate", "待核验事实"],
                  ["interpretation", "解释 / 推断"],
                ],
              },
              reason,
            ]}
            label="保存关键陈述"
            disabled={disabled}
            submit={(v) => post("/claims", { ...v, critical: true })}
          />
        </details>
        {detail.claims.length > 0 && (
          <details>
            <summary>添加原文证据</summary>
            <EvidenceForm
              detail={detail}
              disabled={disabled}
              submit={(v) => post("/evidence", v)}
            />
          </details>
        )}
        <p className="muted">
          已核验材料登记了 {detail.verified_source_roots}{" "}
          个不同来源根；重复转载不增加独立性。仍需人工核对来源间的依赖关系。
        </p>
      </details>
      <div className="editorial-gates">
        <details className="work-panel">
          <summary>价值门 · Important OR Useful</summary>
          <EditorForm
            fields={[
              {
                key: "important",
                label: "Important 是否成立",
                options: [
                  ["false", "暂不成立"],
                  ["true", "成立"],
                ],
              },
              {
                key: "important_reason",
                label: "重要性理由",
                multiline: true,
                optional: true,
              },
              {
                key: "useful",
                label: "Useful 是否成立",
                options: [
                  ["false", "暂不成立"],
                  ["true", "成立"],
                ],
              },
              {
                key: "useful_reason",
                label: "实用性理由",
                multiline: true,
                optional: true,
              },
              {
                key: "status",
                label: "价值判断",
                options: [
                  ["pending", "待判断"],
                  ["passed", "通过"],
                  ["rejected", "淘汰"],
                ],
              },
              reason,
            ]}
            label="保存价值判断"
            disabled={disabled}
            submit={(v) =>
              post("/value", {
                ...v,
                important: v.important === "true",
                useful: v.useful === "true",
              })
            }
          />
        </details>
        <details className="work-panel">
          <summary>质量门 · 证据充分吗</summary>
          <EditorForm
            fields={[
              {
                key: "status",
                label: "质量判断",
                options: [
                  ["pending", "待核实"],
                  ["passed", "通过"],
                  ["rejected", "不通过"],
                ],
              },
              {
                key: "gaps",
                label: "关键缺口与跟进事项（每行一项，通过时留空）",
                multiline: true,
                optional: true,
              },
              ...detail.evidence
                .filter((e) => e.direction === "counter")
                .map((e) => ({
                  key: `conflict:${e.id}`,
                  label: `反面证据处理：${e.quote.slice(0, 90)}`,
                  multiline: true,
                  optional: true,
                })),
              reason,
            ]}
            label="保存质量判断"
            disabled={disabled}
            submit={(v) =>
              post("/quality", {
                status: v.status,
                reason: v.reason,
                gaps: v.gaps
                  .split("\n")
                  .map((x) => x.trim())
                  .filter(Boolean),
                conflict_resolutions: Object.fromEntries(
                  Object.entries(v)
                    .filter(
                      ([k, val]) => k.startsWith("conflict:") && val.trim(),
                    )
                    .map(([k, val]) => [k.slice(9), val]),
                ),
              })
            }
          />
        </details>
      </div>
      <details className="work-panel">
        <summary>编辑决定</summary>
        <EditorForm
          fields={[
            {
              key: "status",
              label: "处理方式",
              options: [
                ["deferred", "待核实"],
                ["selected", "入选，准备后续 Brief"],
                ["evidence_only", "仅存证"],
                ["observe", "继续观察"],
                ["rejected", "驳回"],
              ],
            },
            reason,
          ]}
          label="保存编辑决定"
          disabled={disabled}
          submit={(v) => post("/decision", v)}
        />
      </details>
      <details className="work-panel">
        <summary>
          审核与更正历史 · {detail.reviews.length + detail.history.length} 条
        </summary>
        {detail.reviews.map((r) => (
          <div className="session-card" key={r.id}>
            <strong>
              {
                (
                  {
                    value: "价值判断",
                    quality: "质量判断",
                    decision: "编辑决定",
                  } as Record<string, string>
                )[r.gate]
              }{" "}
              · {states[r.status]}
            </strong>
            <p>
              {r.actor} · {new Date(r.created_at).toLocaleString("zh-CN")} ·
              修订 {r.revision}
              {r.revision !== event.revision ? "（旧内容版本）" : ""}
            </p>
            <pre>{JSON.stringify(r.detail, null, 2)}</pre>
          </div>
        ))}
        {detail.history.map((h) => (
          <div className="session-card" key={h.id}>
            <p>
              {h.actor} · {new Date(h.created_at).toLocaleString("zh-CN")}
            </p>
            <pre>
              {JSON.stringify({ action: h.action, ...h.detail }, null, 2)}
            </pre>
          </div>
        ))}
      </details>
    </div>
  );
}

function MemberForm({
  items,
  disabled,
  submit,
}: {
  items: Item[];
  disabled: boolean;
  submit: (v: Record<string, unknown>) => Promise<void>;
}) {
  const [versionId, setVersionId] = useState("");
  const [original, setOriginal] = useState<Detail | null>(null);
  const [paragraphs, setParagraphs] = useState<string[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setOriginal(null);
    setParagraphs([]);
    setError("");
    if (versionId)
      request<Detail>(`/versions/${versionId}`)
        .then((v) => {
          if (active) setOriginal(v);
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    return () => {
      active = false;
    };
  }, [versionId]);
  return (
    <div className="validation-form">
      <h3>关联一份材料</h3>
      <label>
        选择已保存原文
        <select
          value={versionId}
          onChange={(e) => setVersionId(e.target.value)}
        >
          <option value="">请选择材料</option>
          {items.map((i) => (
            <option value={i.version.id} key={i.version.id}>
              {i.version.title}
            </option>
          ))}
        </select>
      </label>
      {error && <p role="alert">{error}</p>}
      {original && (
        <>
          <fieldset className="paragraph-picker">
            <legend>选择与此事件相关的原文段落</legend>
            {original.version.paragraphs.map((p) => (
              <label className="checkbox-label" key={p.id}>
                <input
                  type="checkbox"
                  checked={paragraphs.includes(p.id)}
                  onChange={(e) =>
                    setParagraphs((v) =>
                      e.target.checked
                        ? [...v, p.id]
                        : v.filter((id) => id !== p.id),
                    )
                  }
                />
                <span>
                  {p.id} · {p.text}
                </span>
              </label>
            ))}
          </fieldset>
          <EditorForm
            key={versionId}
            fields={[reason]}
            label="关联选中段落"
            disabled={disabled || !paragraphs.length}
            submit={(v) =>
              submit({ ...v, version_id: versionId, paragraph_ids: paragraphs })
            }
          />
        </>
      )}
    </div>
  );
}

function EvidenceForm({
  detail,
  disabled,
  submit,
}: {
  detail: EventDetail;
  disabled: boolean;
  submit: (v: Record<string, unknown>) => Promise<void>;
}) {
  const members = detail.members.filter((m) => m.active);
  const [versionId, setVersionId] = useState(members[0]?.version_id || "");
  const [paragraphs, setParagraphs] = useState<string[]>([]);
  const member = members.find((m) => m.version_id === versionId);
  if (!members.length)
    return <p className="muted">先关联原始材料，再添加对应证据。</p>;
  return (
    <div className="validation-form">
      <label>
        证据原文
        <select
          value={versionId}
          onChange={(e) => {
            setVersionId(e.target.value);
            setParagraphs([]);
          }}
        >
          {members.map((m) => (
            <option key={m.id} value={m.version_id}>
              {m.title}
            </option>
          ))}
        </select>
      </label>
      <fieldset className="paragraph-picker">
        <legend>证据所在段落</legend>
        {member?.paragraphs
          .filter((p) => member.paragraph_ids.includes(String(p.id)))
          .map((p) => (
            <label className="checkbox-label" key={String(p.id)}>
              <input
                type="checkbox"
                checked={paragraphs.includes(String(p.id))}
                onChange={(e) =>
                  setParagraphs((v) =>
                    e.target.checked
                      ? [...v, String(p.id)]
                      : v.filter((id) => id !== p.id),
                  )
                }
              />
              <span>
                {String(p.id)} · {String(p.text)}
              </span>
            </label>
          ))}
      </fieldset>
      <EditorForm
        key={versionId}
        fields={[
          {
            key: "claim_id",
            label: "针对哪条陈述",
            options: detail.claims.map((c) => [c.id, c.text]),
          },
          {
            key: "direction",
            label: "证据方向",
            options: [
              ["context", "仅提供背景"],
              ["supporting", "支持"],
              ["counter", "反面 / 限制"],
            ],
          },
          {
            key: "quote",
            label: "原文短摘录（保留原文，不翻译）",
            multiline: true,
          },
          {
            key: "rationale",
            label: "为何支持、反驳或提供背景",
            multiline: true,
          },
          {
            key: "source_root",
            label: "原始来源根（转载填写共同原始出处）",
            initial: member?.url,
          },
          {
            key: "limitations",
            label: "方法、适用范围、来源依赖与利益关联",
            multiline: true,
          },
          reason,
        ]}
        label="保存待核验证据"
        disabled={disabled || !paragraphs.length}
        submit={(v) =>
          submit({ ...v, version_id: versionId, paragraph_ids: paragraphs })
        }
      />
    </div>
  );
}

function EvidenceCard({
  evidence: e,
  member,
  disabled,
  submit,
}: {
  evidence: S["EvidenceView"];
  member: EventDetail["members"][number] | undefined;
  disabled: boolean;
  submit: (v: Record<string, unknown>) => Promise<void>;
}) {
  const [checked, setChecked] = useState(false);
  return (
    <div className="evidence-card">
      <div className="tags">
        <span>{states[e.direction]}</span>
        <span>{states[e.status]}</span>
      </div>
      <blockquote>{e.quote}</blockquote>
      <p>{e.rationale}</p>
      <p className="muted">
        限制：{e.limitations}
        <br />
        来源根：{e.source_root}
      </p>
      {member && (
        <a href={member.url} target="_blank" rel="noreferrer">
          {member.source_name} · 原文 ↗
        </a>
      )}
      <details>
        <summary>核验此证据</summary>
        <p>
          {e.checked_by
            ? `${e.checked_by} · ${new Date(e.checked_at!).toLocaleString("zh-CN")}`
            : "尚未核验"}
        </p>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={checked}
            onChange={(ev) => setChecked(ev.target.checked)}
          />
          我已对照原文、适用范围与来源依赖
        </label>
        <EditorForm
          fields={[
            {
              key: "status",
              label: "证据核验结论",
              options: [
                ["needs_review", "仍需复核"],
                ["verified", "核验通过"],
                ["rejected", "不适用于此陈述"],
              ],
            },
            reason,
          ]}
          label="记录证据核验"
          disabled={disabled}
          submit={(v) => submit({ ...v, original_checked: checked })}
        />
      </details>
    </div>
  );
}
