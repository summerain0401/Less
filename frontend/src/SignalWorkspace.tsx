import { useEffect, useState } from "react";
import { EditorForm, request } from "./editorialForms";
import type { S, Field } from "./editorialForms";
const labels: Record<string, string> = {
  draft: "假设草稿",
  candidate: "Candidate",
  emerging: "Emerging",
  strong: "Strong",
  established: "Established",
  weakening: "Weakening",
  rejected: "Rejected",
  supporting: "支持",
  counter: "反面",
  context: "背景",
  thesis: "假设版本",
  evidence: "证据关联",
  unlink: "取消关联",
  counter_search: "反证检索",
  review: "人工复评",
  source_changed: "来源变化",
};
const thesisFields: Field[] = [
  { key: "title", label: "Signal 名称" },
  { key: "statement", label: "可检验判断", multiline: true },
  { key: "scope", label: "适用人群、任务与边界", multiline: true },
  { key: "starts_on", label: "观察期开始（YYYY-MM-DD）" },
  { key: "ends_on", label: "观察期结束（YYYY-MM-DD）" },
  { key: "falsification", label: "什么结果会削弱或推翻判断", multiline: true },
  { key: "counter_plan", label: "反证检索与后续观察计划", multiline: true },
  { key: "owner", label: "内容负责人" },
];
const reason: Field = { key: "reason", label: "本次变更依据", multiline: true };
export function SignalWorkspace() {
  const [actor, setActor] = useState("");
  const [list, setList] = useState<S["SignalView"][]>([]);
  const [detail, setDetail] = useState<S["SignalDetail"] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function refresh(id?: string) {
    const rows = await request<S["SignalView"][]>("/signals");
    setList(rows);
    if (id) setDetail(await request<S["SignalDetail"]>(`/signals/${id}`));
  }
  useEffect(() => {
    let active = true;
    request<S["SignalView"][]>("/signals")
      .then((v) => {
        if (active) setList(v);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
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
  async function post(
    path: string,
    values: Record<string, unknown>,
    method = "POST",
  ) {
    if (!detail) return;
    await act(async () => {
      await request(
        `/signals/${detail.signal.id}${path}`,
        { ...values, actor, revision: detail.signal.revision },
        method,
      );
      await refresh(detail.signal.id);
    });
  }
  const disabled = busy || !actor.trim();
  const s = detail?.signal;
  return (
    <section className="validation-desk">
      <h2>Signal 工作区</h2>
      <p className="muted">
        从可证伪假设开始，保留支持、反面证据和检索缺口。成熟度由明确复评决定，不能仅凭发布数量升级。
      </p>
      {error && (
        <p className="banner error" role="alert">
          {error}
        </p>
      )}
      <label>
        Signal 编辑姓名
        <input
          value={actor}
          maxLength={80}
          onChange={(e) => setActor(e.target.value)}
        />
      </label>
      <details className="work-panel">
        <summary>建立假设草稿</summary>
        <EditorForm
          fields={thesisFields}
          label="保存 Signal 草稿"
          disabled={disabled}
          submit={(values) =>
            act(async () => {
              const created = await request<S["SignalView"]>("/signals", {
                actor,
                thesis: values,
              });
              await refresh(created.id);
            })
          }
        />
      </details>
      <label>
        选择 Signal
        <select
          disabled={busy}
          value={s?.id ?? ""}
          onChange={(e) => {
            if (e.target.value) void act(() => refresh(e.target.value));
          }}
        >
          <option value="">请选择</option>
          {list.map((v) => (
            <option key={v.id} value={v.id}>
              {String(v.thesis.title)} · {labels[v.status]}
              {v.needs_review ? " · 需复评" : ""}
            </option>
          ))}
        </select>
      </label>
      {detail && s && (
        <>
          <h3>{String(s.thesis.title)}</h3>
          <p>
            {labels[s.status]} · 版本 {s.revision} ·{" "}
            {s.needs_review ? "需要复评" : "已完成本轮复评"}
          </p>
          <p>{String(s.thesis.statement)}</p>
          <p className="muted">
            最近实质复评：
            {s.last_reviewed_at
              ? new Date(s.last_reviewed_at).toLocaleString("zh-CN")
              : "尚无"}
          </p>
          <p>
            适用范围：{String(s.thesis.scope)}
            <br />
            观察期：{String(s.thesis.starts_on)} — {String(s.thesis.ends_on)}
            <br />
            否定条件：{String(s.thesis.falsification)}
            <br />
            反证计划：{String(s.thesis.counter_plan)}
          </p>
          {detail.stale_link_ids.length > 0 && (
            <p className="banner error">
              {detail.stale_link_ids.length}{" "}
              条证据已变化，先在事件中核验，再更新或移除关联。
            </p>
          )}
          <details className="work-panel">
            <summary>修订假设范围</summary>
            <EditorForm
              key={`${s.id}:${s.revision}`}
              fields={[
                ...thesisFields.map((f) => ({
                  ...f,
                  initial: String(s.thesis[f.key] ?? ""),
                })),
                reason,
              ]}
              label="保存假设新版本"
              disabled={disabled}
              submit={(values) => {
                const { reason, ...thesis } = values;
                return post("", { reason, thesis }, "PATCH");
              }}
            />
          </details>
          <details className="work-panel">
            <summary>关联或重新核验证据</summary>
            <SignalEvidencePicker
              key={`${s.id}:${s.revision}`}
              disabled={disabled}
              submit={(v) => post("/evidence", v)}
            />
          </details>
          {(["supporting", "counter", "context"] as const).map((direction) => (
            <div className="work-panel" key={direction}>
              <h3>{labels[direction]}证据</h3>
              {!detail.evidence.some(
                (e) => e.active && e.direction === direction,
              ) && (
                <p className="muted">
                  尚无关联材料。缺少反面证据不代表判断成立。
                </p>
              )}
              {detail.evidence
                .filter((e) => e.direction === direction)
                .map((e) => (
                  <div className="session-card" key={e.id}>
                    <strong>{String(e.snapshot.claim)}</strong>
                    <p>{e.rationale}</p>
                    <blockquote>{String(e.snapshot.quote)}</blockquote>
                    <p className="muted">
                      {String(e.snapshot.limitations)} · 来源根：
                      {String(e.snapshot.source_root)}
                    </p>
                    <p>
                      原始发生时间：
                      {String(
                        e.snapshot.happened_at ??
                          e.snapshot.published_at ??
                          "未知",
                      )}{" "}
                      · 加入时间：{new Date(e.added_at).toLocaleString("zh-CN")}
                    </p>
                    <a
                      href={String(e.snapshot.url)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      原文 ↗
                    </a>
                    {" · "}
                    <a
                      href={`/api/versions/${e.snapshot.version_id}/snapshot`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      保存版本 ↗
                    </a>
                    <p>
                      {!e.active
                        ? "已取消关联，历史保留"
                        : detail.stale_link_ids.includes(e.id)
                          ? "需重新核验"
                          : "关联有效"}
                    </p>
                    {e.active && (
                      <EditorForm
                        fields={[reason]}
                        label="取消证据关联"
                        disabled={disabled}
                        submit={(v) => post(`/evidence/${e.id}/unlink`, v)}
                      />
                    )}
                  </div>
                ))}
            </div>
          ))}
          <details className="work-panel">
            <summary>记录本轮反证检索</summary>
            <p className="muted">
              此处记录已执行的检索，不会代为搜索。写明查了哪里、找到什么、仍缺什么；没找到也如实保留。
            </p>
            <EditorForm
              key={`${s.id}:${s.revision}:search`}
              fields={[
                { key: "query", label: "实际检索词" },
                {
                  key: "source_types",
                  label: "查阅来源类型与范围",
                  multiline: true,
                },
                {
                  key: "results",
                  label: "发现、具体出处或未找到结果",
                  multiline: true,
                },
                { key: "gaps", label: "检索缺口与覆盖限制", multiline: true },
                reason,
              ]}
              label="保存反证检索记录"
              disabled={disabled}
              submit={(v) => post("/searches", v)}
            />
          </details>
          <details className="work-panel">
            <summary>人工复评与 Our View</summary>
            <SignalReview
              key={`${s.id}:${s.revision}:review`}
              detail={detail}
              disabled={disabled}
              submit={(v) => post("/reviews", v)}
            />
          </details>
          <div className="work-panel">
            <h3>Timeline · 版本与判断历史</h3>
            {detail.records
              .slice()
              .reverse()
              .map((r) => (
                <details key={r.id}>
                  <summary>
                    {new Date(r.created_at).toLocaleString("zh-CN")} ·{" "}
                    {labels[r.kind]} · {r.actor}
                  </summary>
                  <p>{r.reason}</p>
                  {r.kind === "review" && (
                    <>
                      <p>
                        {labels[String(r.detail.previous_status)]} →{" "}
                        {labels[String(r.detail.status)]}
                      </p>
                      <h4>Our View</h4>
                      <p>{String(r.detail.our_view)}</p>
                      <p>独立性：{String(r.detail.independence)}</p>
                      <p>替代解释：{String(r.detail.alternatives)}</p>
                    </>
                  )}
                  {r.kind === "counter_search" && (
                    <>
                      <p>检索：{String(r.detail.query)}</p>
                      <p>范围：{String(r.detail.source_types)}</p>
                      <p>发现：{String(r.detail.results)}</p>
                      <p>缺口：{String(r.detail.gaps)}</p>
                    </>
                  )}
                  {r.kind === "thesis" &&
                    Object.entries(
                      (r.detail.thesis ?? {}) as Record<string, unknown>,
                    ).map(([key, value]) => (
                      <p key={key}>
                        {thesisFields.find((f) => f.key === key)?.label ?? key}
                        ：{String(value)}
                      </p>
                    ))}
                </details>
              ))}
          </div>
        </>
      )}
    </section>
  );
}
function SignalEvidencePicker({
  disabled,
  submit,
}: {
  disabled: boolean;
  submit: (v: Record<string, unknown>) => Promise<void>;
}) {
  const [events, setEvents] = useState<S["EventView"][]>([]);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [event, setEvent] = useState<S["EventDetail"] | null>(null);
  const [id, setId] = useState("");
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    request<S["InboxView"]>(`/editorial/events?offset=${offset}`)
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
  }, [offset]);
  useEffect(() => {
    let active = true;
    setEvent(null);
    setChecked(false);
    if (id)
      request<S["EventDetail"]>(`/editorial/events/${id}`)
        .then((v) => {
          if (active) setEvent(v);
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    return () => {
      active = false;
    };
  }, [id]);
  const evidence = event?.evidence.filter((e) => e.status === "verified") ?? [];
  return (
    <div>
      {error && <p role="alert">{error}</p>}
      <label>
        证据所属事件
        <select value={id} onChange={(e) => setId(e.target.value)}>
          <option value="">请选择事件</option>
          {events.map((e) => (
            <option key={e.id} value={e.id}>
              {e.title}
            </option>
          ))}
        </select>
      </label>
      <div className="validation-actions">
        <button disabled={offset === 0} onClick={() => setOffset(offset - 50)}>
          上一页事件
        </button>
        <button
          disabled={offset + 50 >= total}
          onClick={() => setOffset(offset + 50)}
        >
          下一页事件
        </button>
      </div>
      {evidence.length ? (
        <>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
            />
            我已核对原文及其对假设的作用
          </label>
          <EditorForm
            key={id}
            fields={[
              {
                key: "evidence_id",
                label: "选择已核验证据",
                options: evidence.map((e) => [e.id, e.quote]),
              },
              {
                key: "direction",
                label: "对假设的证据方向",
                options: [
                  ["context", "背景"],
                  ["supporting", "支持"],
                  ["counter", "反面"],
                ],
              },
              {
                key: "rationale",
                label: "针对假设哪一部分，为何支持或反驳",
                multiline: true,
              },
              reason,
            ]}
            label="保存证据关联"
            disabled={disabled || !checked}
            submit={(v) => submit({ ...v, original_checked: checked })}
          />
        </>
      ) : (
        <p className="muted">选择事件后，使用在编辑收件箱中已核验的证据。</p>
      )}
    </div>
  );
}
function SignalReview({
  detail,
  disabled,
  submit,
}: {
  detail: S["SignalDetail"];
  disabled: boolean;
  submit: (v: Record<string, unknown>) => Promise<void>;
}) {
  const [checked, setChecked] = useState(false);
  return (
    <div>
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => setChecked(e.target.checked)}
        />
        已复核原文、独立性和适用范围
      </label>
      <EditorForm
        fields={[
          {
            key: "status",
            label: "复评后状态",
            options: [
              "candidate",
              "emerging",
              "strong",
              "established",
              "weakening",
              "rejected",
            ].map((s) => [s, labels[s]]),
          },
          {
            key: "our_view",
            label: "Our View · 当前判断与未知",
            multiline: true,
          },
          {
            key: "independence",
            label: "来源独立性与证据适用范围",
            multiline: true,
          },
          { key: "alternatives", label: "主要替代解释", multiline: true },
          {
            key: "maturity_evidence",
            label:
              "跨时间、主体、类型与持续验证依据（Strong / Established 必填）",
            multiline: true,
            optional: true,
          },
          ...detail.evidence
            .filter((e) => e.active && e.direction === "counter")
            .map((e) => ({
              key: `counter:${e.id}`,
              label: `反证处理：${e.rationale}`,
              multiline: true,
            })),
          reason,
        ]}
        label="记录本轮复评"
        disabled={disabled || !checked}
        submit={(values) => {
          const {
            status,
            our_view,
            independence,
            alternatives,
            maturity_evidence,
            reason,
          } = values;
          return submit({
            status,
            our_view,
            independence,
            alternatives,
            maturity_evidence,
            reason,
            original_checked: checked,
            counter_resolutions: Object.fromEntries(
              Object.entries(values)
                .filter(([k]) => k.startsWith("counter:"))
                .map(([k, v]) => [k.slice(8), v]),
            ),
          });
        }}
      />
    </div>
  );
}
