import { useEffect, useState } from "react";
import { EditorForm, request, skeleton, reason } from "./editorialForms";
import type { S, EventDetail } from "./editorialForms";

export function ClusterSuggestions({
  onOpen,
}: {
  onOpen: (id: string) => void;
}) {
  const [data, setData] = useState<S["ClusterSuggestionsView"] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function refresh() {
    setBusy(true);
    setError("");
    try {
      setData(
        await request<S["ClusterSuggestionsView"]>(
          "/editorial/cluster-suggestions",
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="work-panel">
      <summary>事件聚类建议 · 先检查差异</summary>
      <p className="muted">
        按事件骨架寻找可能相关的事件。建议不会自动合并，也不代表证据已通过核验。
      </p>
      <button disabled={busy} onClick={() => void refresh()}>
        刷新聚类建议
      </button>
      {error && <p role="alert">聚类服务暂不可用：{error}</p>}
      {data && (
        <>
          <p className="muted">
            已比较 {data.considered_events} / {data.total_events} 个事件，找到{" "}
            {data.total_pairs} 对候选；展示前 {data.pairs.length} 对。
          </p>
          {data.pairs.map((pair) => (
            <div
              className="session-card"
              key={`${pair.left.id}:${pair.right.id}`}
            >
              <strong>
                {
                  (
                    {
                      same_candidate: "可能同一事件",
                      different: "存在拆分线索",
                      uncertain: "尚不确定",
                    } as Record<string, string>
                  )[pair.suggestion]
                }
              </strong>
              <div className="validation-actions">
                <button onClick={() => onOpen(pair.left.id)}>
                  {pair.left.title}
                </button>
                <button onClick={() => onOpen(pair.right.id)}>
                  {pair.right.title}
                </button>
              </div>
              <p>{pair.reasons.join("；") || "缺少共同线索"}</p>
              {pair.conflicts.length > 0 && (
                <p className="cluster-conflicts">{pair.conflicts.join("；")}</p>
              )}
              <small>
                规则相似度 {Math.round(pair.score * 100)}% · 不是同事件概率
              </small>
            </div>
          ))}
          <details>
            <summary>建议的适用边界</summary>
            {data.limitations.map((text) => (
              <p key={text}>{text}</p>
            ))}
          </details>
        </>
      )}
    </details>
  );
}

type Props = {
  detail: EventDetail;
  actor: string;
  busy: boolean;
  act: (fn: () => Promise<unknown>) => Promise<void>;
  onOpen: (id: string) => void;
};
export function EventClusterTools({ detail, actor, busy, act, onOpen }: Props) {
  const event = detail.event;
  const [others, setOthers] = useState<S["EventView"][]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [chosen, setChosen] = useState<S["EventView"][]>([]);
  const [targetId, setTargetId] = useState(event.id);
  const [members, setMembers] = useState<string[]>([]);
  const [claims, setClaims] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const operations = detail.cluster_operations ?? [];
  const active = (event.lifecycle ?? "active") === "active";
  const disabled = busy || !actor.trim();
  useEffect(() => {
    if (!active || detail.cluster_operations === undefined) return;
    let alive = true;
    request<S["InboxView"]>(`/editorial/events?limit=50&offset=${offset}`)
      .then((result) => {
        if (alive) {
          setOthers(result.events.filter((e) => e.id !== event.id));
          setTotal(result.total);
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [active, detail.cluster_operations, event.id, offset]);
  if (detail.cluster_operations === undefined)
    return <p className="muted">聚类操作将在服务更新后可用。</p>;
  return (
    <details className="work-panel">
      <summary>合并、拆分与恢复</summary>
      <p className="muted">
        操作保留原始材料与旧事件去向，陈述和证据保留
        ID。操作后需重新核验；已有后续内容修改时不能直接恢复旧快照。
      </p>
      {error && <p role="alert">{error}</p>}
      {active && (
        <>
          <details>
            <summary>与其他事件合并</summary>
            <fieldset>
              <legend>选择要合并的其他事件</legend>
              {others.map((other) => (
                <label className="checkbox-label" key={other.id}>
                  <input
                    type="checkbox"
                    checked={chosen.some((c) => c.id === other.id)}
                    onChange={(e) => {
                      setChosen((current) =>
                        e.target.checked
                          ? [...current, other]
                          : current.filter((c) => c.id !== other.id),
                      );
                      if (!e.target.checked && targetId === other.id)
                        setTargetId(event.id);
                    }}
                  />
                  {other.title} · {other.subject} / {other.action} /{" "}
                  {other.event_version || "版本未知"}
                </label>
              ))}
            </fieldset>
            <div className="validation-actions">
              <button
                disabled={offset === 0 || busy}
                onClick={() => setOffset(Math.max(0, offset - 50))}
              >
                上一批事件
              </button>
              <span className="muted">已选 {chosen.length} 个其他事件</span>
              <button
                disabled={offset + 50 >= total || busy}
                onClick={() => setOffset(offset + 50)}
              >
                下一批事件
              </button>
            </div>
            <form
              className="validation-form"
              onSubmit={(e) => {
                e.preventDefault();
                void act(() =>
                  request("/editorial/clusters/merge", {
                    actor,
                    reason: note,
                    target_id: targetId,
                    events: [event, ...chosen].map((e) => ({
                      id: e.id,
                      revision: e.revision,
                    })),
                  }),
                );
              }}
            >
              <label>
                保留哪个事件作为主记录
                <select
                  aria-label="保留哪个事件作为主记录"
                  value={targetId}
                  onChange={(e) => setTargetId(e.target.value)}
                >
                  {[event, ...chosen].map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.title}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                合并依据
                <textarea
                  required
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="说明主体、动作、时间和版本为何指向同一事件"
                />
              </label>
              <button
                disabled={
                  disabled ||
                  !chosen.length ||
                  chosen.length > 19 ||
                  !note.trim()
                }
                type="submit"
              >
                合并选中事件
              </button>
            </form>
          </details>
          <details>
            <summary>拆出独立事件</summary>
            <fieldset>
              <legend>选择拆出的原文关联</legend>
              {detail.members
                .filter((m) => m.active)
                .map((m) => (
                  <label className="checkbox-label" key={m.id}>
                    <input
                      type="checkbox"
                      checked={members.includes(m.id)}
                      onChange={(e) =>
                        setMembers((current) =>
                          e.target.checked
                            ? [...current, m.id]
                            : current.filter((id) => id !== m.id),
                        )
                      }
                    />
                    {m.title}
                  </label>
                ))}
            </fieldset>
            <fieldset>
              <legend>选择要移动的陈述（可为空）</legend>
              {detail.claims.map((c) => (
                <label className="checkbox-label" key={c.id}>
                  <input
                    type="checkbox"
                    checked={claims.includes(c.id)}
                    onChange={(e) => {
                      setClaims((current) =>
                        e.target.checked
                          ? [...current, c.id]
                          : current.filter((id) => id !== c.id),
                      );
                      if (e.target.checked) {
                        const needed = new Set(
                          detail.evidence
                            .filter((x) => x.claim_id === c.id)
                            .map((x) => x.version_id),
                        );
                        setMembers((current) => [
                          ...new Set([
                            ...current,
                            ...detail.members
                              .filter(
                                (m) => m.active && needed.has(m.version_id),
                              )
                              .map((m) => m.id),
                          ]),
                        ]);
                      }
                    }}
                  />
                  {c.text}
                </label>
              ))}
            </fieldset>
            <p className="muted">
              移走陈述时会一起移动它的证据；若原事件的其他陈述仍引用同一材料，原关联也会保留。
            </p>
            <EditorForm
              fields={[
                ...skeleton.map((f) => ({
                  ...f,
                  initial:
                    f.key === "title"
                      ? `${event.title}（拆分）`
                      : String(event[f.key as keyof typeof event] ?? ""),
                })),
                reason,
              ]}
              label="创建拆分事件"
              disabled={disabled || !members.length}
              submit={(values) =>
                act(() =>
                  request(`/editorial/events/${event.id}/split`, {
                    actor,
                    revision: event.revision,
                    reason: values.reason,
                    member_ids: members,
                    claim_ids: claims,
                    target: {
                      ...Object.fromEntries(
                        Object.entries(values).filter(
                          ([key]) => key !== "reason",
                        ),
                      ),
                      event_version: values.event_version || null,
                      happened_at: event.happened_at,
                    },
                  }),
                )
              }
            />
          </details>
        </>
      )}
      <h3>聚类操作历史</h3>
      {!operations.length && <p className="muted">暂无合并或拆分记录</p>}
      {operations.map((operation) => (
        <div className="session-card" key={operation.id}>
          <strong>
            {operation.kind === "merge" ? "合并" : "拆分"} ·{" "}
            {operation.status === "restored" ? "已恢复" : "已应用"}
          </strong>
          <p>
            {operation.actor} ·{" "}
            {new Date(operation.created_at).toLocaleString("zh-CN")}
          </p>
          <p>{operation.reason}</p>
          <div className="validation-actions">
            {Object.keys(operation.after_revisions)
              .filter((id) => id !== event.id)
              .map((id, i) => (
                <button key={id} onClick={() => onOpen(id)}>
                  查看关联事件 {i + 1}
                </button>
              ))}
          </div>
          {operation.status === "applied" ? (
            <EditorForm
              fields={[{ ...reason, label: "恢复依据" }]}
              label="恢复本次聚类操作"
              disabled={disabled}
              submit={(v) =>
                act(() =>
                  request(`/editorial/clusters/${operation.id}/restore`, {
                    actor,
                    reason: v.reason,
                  }),
                )
              }
            />
          ) : (
            <p>
              恢复人：{operation.restored_by} · {operation.restore_reason}
            </p>
          )}
        </div>
      ))}
    </details>
  );
}
