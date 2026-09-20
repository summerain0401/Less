import { useCallback, useEffect, useState } from "react";
import type { components } from "./api.generated";
import type { Source } from "./types";

type S = components["schemas"];
type Report = S["DailyReportView"];
type Batch = S["BatchView"];
type BatchDetail = S["BatchDetail"];
type Sample = S["SampleDetail"];
type Session = S["SessionView"];
type Field = S["FieldInput"];
const displayTime = (s: string) =>
  new Date(s).toLocaleString("zh-CN", { hour12: false });
const percent = (n: number | null) =>
  n === null ? "待核查" : `${(n * 100).toFixed(1)}%`;
const states: Record<string, string> = {
  not_prepared: "待准备",
  pending: "等待提取",
  running: "提取中",
  retryable: "等待重试",
  budget_wait: "等待次日额度",
  blocked: "AI 已暂停",
  succeeded: "可核查",
  failed: "提取失败",
};
const modes: Record<string, string> = {
  baseline: "手工筛选基线",
  system: "使用 Less",
  setup: "配置与维护",
};
async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(
    `/api/validation${path}`,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string" ? data.detail : "请检查填写内容后重试",
    );
  return data;
}

export function ValidationDesk({ sources }: { sources: Source[] }) {
  const [report, setReport] = useState<Report | null>(null);
  const [day, setDay] = useState("");
  const [batches, setBatches] = useState<Batch[]>([]);
  const [batchId, setBatchId] = useState("");
  const [batch, setBatch] = useState<BatchDetail | null>(null);
  const [sampleId, setSampleId] = useState("");
  const [sample, setSample] = useState<Sample | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [actor, setActor] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const refresh = useCallback(async () => {
    const [r, b, s, detail, current] = await Promise.all([
      request<Report>(`/report${day ? `?day=${day}` : ""}`),
      request<Batch[]>("/batches"),
      request<Session[]>("/sessions"),
      batchId ? request<BatchDetail>(`/batches/${batchId}`) : null,
      sampleId ? request<Sample>(`/samples/${sampleId}`) : null,
    ]);
    return { r, b, s, detail, current };
  }, [day, batchId, sampleId]);
  const update = useCallback(
    (data: Awaited<ReturnType<typeof refresh>>) => {
      setReport(data.r);
      setBatches(data.b);
      setSessions(data.s);
      setBatch(data.detail);
      setSample(data.current);
      if (!batchId && data.b.length) setBatchId(data.b[0].id);
    },
    [batchId],
  );
  useEffect(() => {
    let alive = true;
    const load = () =>
      refresh()
        .then((data) => {
          if (alive) update(data);
        })
        .catch((e) => {
          if (alive) setError(e.message);
        });
    void load();
    const timer = setInterval(load, 8000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [refresh, update]);
  async function act(fn: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
      update(await refresh());
      setNotice(message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="validation-desk">
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
        <h2>每日运行与验收</h2>
        <div className="validation-actions">
          <label>
            统计日期{" "}
            <input
              type="date"
              aria-label="统计日期"
              value={day || report?.date || ""}
              onChange={(e) => setDay(e.target.value)}
            />
          </label>
          <a
            href={`/api/validation/report.md${day ? `?day=${day}` : ""}`}
            download={`less-${day || report?.date || "today"}.md`}
          >
            导出日报 ↓
          </a>
        </div>
      </div>
      {report && (
        <>
          <div className="validation-stats">
            <div>
              <span>计划采集成功率</span>
              <strong>
                {report.success_rate === null
                  ? "暂无任务"
                  : percent(report.success_rate)}
              </strong>
              <small>
                {report.succeeded} / {report.planned} 次应执行 · 手动采集另计{" "}
                {report.manual_checks} 次
              </small>
            </div>
            <div>
              <span>完整人工抽查 · 累计</span>
              <strong>
                {report.quality.fully_reviewed_samples} <em>/ 30</em>
              </strong>
              <small>
                {report.quality.checked_fields} 个已查字段 · 准确率{" "}
                {percent(report.quality.accuracy)}
              </small>
            </div>
            <div>
              <span>手工筛选基线 · 累计</span>
              <strong>
                {report.baseline_sessions} <em>/ 2</em>
              </strong>
              <small>需记录相同来源范围与筛选标准</small>
            </div>
            <div>
              <span>当日 AI 调用</span>
              <strong>
                {report.budget.used} <em>/ {report.budget.limit}</em>
              </strong>
              <small>重试计入额度 · 次日自动恢复等待任务</small>
            </div>
          </div>
          <p className="muted">
            {report.timezone} ·{" "}
            {report.closed ? "完整日窗口" : "今日记录仍在累积"} · 新材料{" "}
            {report.raw_items} 条，完成提取 {report.normalized} 条。缺少调度记录{" "}
            {report.unrecorded_due} 次。样本或观察天数不足时，不代表验收通过。
          </p>
          <details>
            <summary>统计口径与人工耗时</summary>
            <p>
              成功率按当日应执行的计划采集计算；只有在该统计日结束前完成的任务计为成功。手动采集不计入分母。来源状态、人工验收进度为当前累计记录。
            </p>
            <p>
              已结束工作：
              {Object.entries(report.work_seconds)
                .map(
                  ([mode, seconds]) =>
                    `${modes[mode]} ${(seconds / 60).toFixed(1)} 分钟`,
                )
                .join("；") || "暂无"}
              。未结束 {report.active_sessions} 项。
            </p>
            <p>
              已观测 {report.observed_tokens.toLocaleString()} token；
              {report.cost_note}。历史调用估算 {report.budget.legacy_estimated}{" "}
              次。Event / Candidate / Brief 指标尚未建立。
            </p>
          </details>
        </>
      )}
      <div className="validation-identity">
        <label>
          操作人
          <input
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            placeholder="填写你的名字，用于操作记录"
            maxLength={80}
          />
        </label>
      </div>
      <details className="work-panel">
        <summary>人工工作计时 · 基线与使用 Less 的对照</summary>
        <p className="muted">
          开始后再开展实际工作；结束时填写阅读量、候选数与入选数。两次基线应使用一致的来源范围与
          Important OR Useful 标准。
        </p>
        <SessionStart
          sources={sources}
          actor={actor}
          busy={busy}
          onStart={(body) =>
            act(
              () => request("/sessions", body),
              "计时已开始，请按记录的范围开展工作",
            )
          }
        />
        {sessions.map((session) => (
          <div className="session-card" key={session.id}>
            <strong>
              {session.reviewer} · {modes[session.mode]}
            </strong>
            <small>
              {displayTime(session.started_at)} →{" "}
              {session.ended_at ? displayTime(session.ended_at) : "计时中"}
            </small>
            <p>{session.criteria}</p>
            <p className="muted">
              {session.source_ids
                .map((id) => sources.find((s) => s.id === id)?.name || id)
                .join(" · ")}
            </p>
            {session.ended_at ? (
              <p>
                阅读 {session.read_count} · 候选 {session.candidate_count} ·
                入选 {session.selected_count}
                <br />
                {session.note}
              </p>
            ) : (
              <SessionStop
                busy={busy}
                onStop={(body) =>
                  act(
                    () => request(`/sessions/${session.id}/stop`, body),
                    "本次工作记录已保存",
                  )
                }
              />
            )}
          </div>
        ))}
      </details>
      <div className="section-heading validation-batch-heading">
        <h2>跨来源抽查</h2>
        <button
          disabled={busy || !actor.trim()}
          onClick={() =>
            void act(async () => {
              const created = await request<BatchDetail>("/batches", {
                actor,
                target_count: 30,
              });
              setBatchId(created.batch.id);
              setSampleId("");
              setSample(null);
            }, "已固定抽样清单；准备提取后即可逐条核查")
          }
        >
          新建 30 条抽样
        </button>
      </div>
      <p className="muted">
        每个 Item
        只抽取一个最新保存版本，按来源分散随机抽取；先固定样本，再处理提取结果。不会自动判定正确。
      </p>
      {batches.length > 0 && (
        <label className="batch-selector">
          抽查批次
          <select
            value={batchId}
            disabled={busy}
            onChange={(e) => {
              setBatchId(e.target.value);
              setBatch(null);
              setSampleId("");
              setSample(null);
            }}
          >
            {batches.map((b) => (
              <option key={b.id} value={b.id}>
                {displayTime(b.created_at)} · {b.sample_count} 条 /{" "}
                {b.source_count} 个来源 · {b.actor}
              </option>
            ))}
          </select>
        </label>
      )}
      {!batches.length && (
        <div className="empty">
          <h3>准备第一批人工抽查</h3>
          <p>填写操作人并创建抽样清单，提取任务将遵守每日调用上限。</p>
        </div>
      )}
      {batch && (
        <>
          <div className="validation-actions batch-actions">
            <span className="muted">
              抽样总体 {batch.batch.population_count} 条 · 已固定{" "}
              {batch.batch.sample_count} 条
            </span>
            <button
              disabled={
                busy || !actor.trim() || !batch.samples.some((s) => !s.run_id)
              }
              onClick={() =>
                void act(
                  () =>
                    request(`/batches/${batchId}/prepare`, {
                      actor,
                      limit: 100,
                    }),
                  "样本已加入提取队列，按每日额度处理",
                )
              }
            >
              准备本批提取
            </button>
          </div>
          {sampleId ? (
            <>
              <button
                className="back"
                onClick={() => {
                  setSampleId("");
                  setSample(null);
                }}
              >
                ← 返回抽样清单
              </button>
              {sample ? (
                <SampleReview
                  key={`${sample.sample.id}:${sample.sample.run_id}:${sample.sample.status}`}
                  detail={sample}
                  actor={actor}
                  busy={busy}
                  onSave={(body) =>
                    act(
                      () => request(`/samples/${sampleId}/reviews`, body),
                      "字段核查已保存，历史记录保持可追溯",
                    )
                  }
                  onRerun={() =>
                    act(
                      () => request(`/samples/${sampleId}/rerun`, { actor }),
                      "已重新提取；之前的核查仍绑定原结果",
                    )
                  }
                />
              ) : (
                <p className="muted">正在读取样本…</p>
              )}
            </>
          ) : (
            <div className="item-list">
              {batch.samples.map((s) => (
                <button
                  className="item-row"
                  key={s.id}
                  onClick={() => {
                    setSampleId(s.id);
                    setSample(null);
                  }}
                >
                  <div className="item-meta">
                    <span>
                      {String(s.position + 1).padStart(2, "0")} /{" "}
                      {s.source_name}
                    </span>
                    <span>
                      {states[s.status] || s.status}
                      {s.reviewed ? " · 有核查记录" : ""}
                    </span>
                  </div>
                  <h3>{s.title}</h3>
                  <span className="muted">打开原文与字段清单 →</span>
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}

function SampleReview({
  detail,
  actor,
  busy,
  onSave,
  onRerun,
}: {
  detail: Sample;
  actor: string;
  busy: boolean;
  onSave: (body: S["FieldReviewInput"]) => Promise<void>;
  onRerun: () => Promise<void>;
}) {
  const [fields, setFields] = useState<Field[]>(
    detail.fields.map((f) => ({
      key: f.key,
      verdict: "not_checked",
      note: "",
    })),
  );
  const [checked, setChecked] = useState(false);
  const [note, setNote] = useState("");
  const allowed = detail.sample.status === "succeeded";
  const valid =
    checked &&
    actor.trim() &&
    fields.some((f) => f.verdict !== "not_checked") &&
    fields.every((f) => f.verdict !== "incorrect" || f.note?.trim());
  function change(index: number, patch: Partial<Field>) {
    setFields((current) =>
      current.map((f, i) => (i === index ? { ...f, ...patch } : f)),
    );
  }
  return (
    <div className="sample-review">
      <h2>{detail.original.title}</h2>
      <div className="validation-actions">
        <a href={detail.original.url} target="_blank" rel="noreferrer">
          打开原始页面 ↗
        </a>
        <a
          href={`/api/versions/${detail.original.id}/snapshot`}
          target="_blank"
          rel="noreferrer"
        >
          保存快照 ↗
        </a>
        <span className="muted">
          {states[detail.sample.status] || detail.sample.status}
        </span>
        <button
          disabled={
            busy ||
            !actor.trim() ||
            [
              "pending",
              "running",
              "retryable",
              "budget_wait",
              "blocked",
            ].includes(detail.sample.status)
          }
          onClick={() => void onRerun()}
        >
          重新提取
        </button>
      </div>
      <div className="comparison validation-comparison">
        <article>
          <div className="panel-label">原文 · 保存版本</div>
          {detail.original.paragraphs.map((p) => (
            <div className="paragraph" key={p.id} id={`validation-${p.id}`}>
              <a href={`#validation-${p.id}`}>{p.id}</a>
              <p>{p.text}</p>
            </div>
          ))}
        </article>
        <article>
          <div className="panel-label">逐字段核查</div>
          {!allowed && (
            <p className="muted">
              等待提取成功后，可记录字段准确率。提取失败的样本仍保留在本批次。
            </p>
          )}
          {detail.fields.map((f, index) => (
            <div className="field-check" key={f.key}>
              <label>
                <strong>{f.label}</strong>
                <p>
                  {Array.isArray(f.value)
                    ? f.value.join(" · ") || "未知 / 空值"
                    : (f.value ?? "未知")}
                </p>
                <select
                  aria-label={`核查：${f.label}`}
                  disabled={!allowed || busy}
                  value={fields[index].verdict}
                  onChange={(e) =>
                    change(index, {
                      verdict: e.target.value as Field["verdict"],
                    })
                  }
                >
                  <option value="not_checked">尚未核查</option>
                  <option value="correct">正确</option>
                  {f.allows_unknown && (
                    <option value="unknown_correct">正确保留未知</option>
                  )}
                  <option value="incorrect">有误，需修正</option>
                </select>
              </label>
              <textarea
                aria-label={`依据：${f.label}`}
                disabled={!allowed || busy}
                value={fields[index].note}
                onChange={(e) => change(index, { note: e.target.value })}
                placeholder={
                  fields[index].verdict === "incorrect"
                    ? "必填：问题及原文修正依据"
                    : "核查依据（可选）"
                }
              />
            </div>
          ))}
          {detail.output && (
            <details>
              <summary>查看提取结果与引用段落</summary>
              <pre>{JSON.stringify(detail.output, null, 2)}</pre>
            </details>
          )}
        </article>
      </div>
      <form
        className="validation-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (allowed && valid && detail.sample.run_id)
            void onSave({
              run_id: detail.sample.run_id,
              reviewer: actor,
              fields,
              note,
              original_checked: checked,
            });
        }}
      >
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={checked}
            disabled={!allowed}
            onChange={(e) => setChecked(e.target.checked)}
          />
          我已对照原始材料，判断以上字段
        </label>
        <label>
          本次核查备注
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={5000}
          />
        </label>
        <button disabled={busy || !allowed || !valid} type="submit">
          保存字段核查
        </button>
        <p className="muted">
          未查字段不计入准确率；只有全部字段完成核查，才计入 30 条完整抽查。
        </p>
      </form>
      {detail.reviews.length > 0 && (
        <details className="review-history">
          <summary>字段核查历史 · {detail.reviews.length} 条</summary>
          {detail.reviews.map((r) => (
            <div className="session-card" key={r.id}>
              <strong>
                {r.reviewer} · {displayTime(r.created_at)}
              </strong>
              <p>
                {r.run_id === detail.sample.run_id
                  ? "当前提取结果"
                  : "先前提取结果"}{" "}
                · 核查{" "}
                {r.fields.filter((f) => f.verdict !== "not_checked").length}{" "}
                个字段
              </p>
              <p>{r.note}</p>
              <pre>{JSON.stringify(r.fields, null, 2)}</pre>
            </div>
          ))}
        </details>
      )}
    </div>
  );
}

function SessionStart({
  sources,
  actor,
  busy,
  onStart,
}: {
  sources: Source[];
  actor: string;
  busy: boolean;
  onStart: (body: S["SessionInput"]) => Promise<void>;
}) {
  const [mode, setMode] = useState<S["SessionInput"]["mode"]>("baseline");
  const [category, setCategory] =
    useState<S["SessionInput"]["category"]>("screening");
  const [scope, setScope] = useState<string[]>([]);
  const [criteria, setCriteria] = useState(
    "按 Important OR Useful 筛选 AI Coding / Agents 材料，证据质量单独核对。",
  );
  return (
    <form
      className="validation-form"
      onSubmit={(e) => {
        e.preventDefault();
        void onStart({
          reviewer: actor,
          mode,
          category,
          source_ids: scope,
          criteria,
        });
      }}
    >
      <div className="form-columns">
        <label>
          工作方式
          <select
            value={mode}
            onChange={(e) => {
              setMode(e.target.value as typeof mode);
              if (e.target.value === "baseline") setCategory("screening");
            }}
          >
            {Object.entries(modes).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          工作类别
          <select
            value={category}
            disabled={mode === "baseline"}
            onChange={(e) => setCategory(e.target.value as typeof category)}
          >
            {Object.entries({
              screening: "筛选",
              review: "复核",
              sources: "来源管理",
              recovery: "故障恢复",
              other: "其他",
            }).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>
      <fieldset>
        <legend>本次来源范围</legend>
        <div className="source-options">
          {sources.map((s) => (
            <label className="checkbox-label" key={s.id}>
              <input
                type="checkbox"
                checked={scope.includes(s.id)}
                onChange={(e) =>
                  setScope((current) =>
                    e.target.checked
                      ? [...current, s.id]
                      : current.filter((id) => id !== s.id),
                  )
                }
              />
              {s.name}
            </label>
          ))}
        </div>
      </fieldset>
      <label>
        筛选标准与工作范围
        <textarea
          required
          value={criteria}
          maxLength={2000}
          onChange={(e) => setCriteria(e.target.value)}
        />
      </label>
      <button
        disabled={busy || !actor.trim() || !scope.length || !criteria.trim()}
        type="submit"
      >
        开始计时
      </button>
    </form>
  );
}

function SessionStop({
  busy,
  onStop,
}: {
  busy: boolean;
  onStop: (body: S["StopInput"]) => Promise<void>;
}) {
  const [counts, setCounts] = useState({
    read_count: "",
    candidate_count: "",
    selected_count: "",
  });
  const [note, setNote] = useState("");
  const valid =
    Object.values(counts).every(
      (n) => n !== "" && Number.isInteger(Number(n)) && Number(n) >= 0,
    ) &&
    Number(counts.selected_count) <= Number(counts.candidate_count) &&
    Number(counts.candidate_count) <= Number(counts.read_count);
  return (
    <form
      className="validation-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid)
          void onStop({
            read_count: Number(counts.read_count),
            candidate_count: Number(counts.candidate_count),
            selected_count: Number(counts.selected_count),
            note,
          });
      }}
    >
      <div className="form-columns">
        {(["read_count", "candidate_count", "selected_count"] as const).map(
          (key, i) => (
            <label key={key}>
              {["阅读量", "候选数", "入选数"][i]}
              <input
                type="number"
                required
                min={0}
                step={1}
                value={counts[key]}
                onChange={(e) =>
                  setCounts({ ...counts, [key]: e.target.value })
                }
              />
            </label>
          ),
        )}
      </div>
      <label>
        工作记录与可定位的结果
        <textarea
          required
          maxLength={5000}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="记录入选材料、问题或中断情况"
        />
      </label>
      <button disabled={busy || !valid || !note.trim()} type="submit">
        结束并保存计时
      </button>
    </form>
  );
}
