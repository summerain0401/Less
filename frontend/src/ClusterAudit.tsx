import { useState } from "react";
import { EditorForm, request } from "./editorialForms";
import type { S } from "./editorialForms";

type FrozenSide = {
  event: {
    title: string;
    subject: string;
    action: string;
    object: string;
    scope: string;
    event_version: string | null;
    happened_at: string | null;
  };
  materials: {
    version_id: string;
    title: string;
    url: string;
    source: string;
    paragraphs: { id: string; text: string }[];
  }[];
};
const verdicts: Record<string, string> = {
  same: "同一事件",
  different: "不同事件",
  uncertain: "无法判断",
  same_candidate: "可能同一事件",
  not_retrieved: "未召回",
};

export function ClusterAudit({ actor }: { actor: string }) {
  const [batches, setBatches] = useState<S["ClusterAuditBatchView"][]>([]);
  const [detail, setDetail] = useState<S["AuditDetail"] | null>(null);
  const [position, setPosition] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
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
  async function load(id: string) {
    setDetail(
      await request<S["AuditDetail"]>(`/editorial/cluster-audits/${id}`),
    );
    setPosition(0);
  }
  const pair = detail?.pairs[position];
  return (
    <details className="work-panel">
      <summary>聚类抽样与盲判</summary>
      <p className="muted">
        固定事件骨架及关联材料，首次提交前隐藏机器结果。当前评估规则建议；不自动合并事件或通过内容审核。
      </p>
      {error && <p role="alert">{error}</p>}
      <button
        disabled={busy}
        onClick={() =>
          void act(async () =>
            setBatches(
              await request<S["ClusterAuditBatchView"][]>(
                "/editorial/cluster-audits",
              ),
            ),
          )
        }
      >
        读取抽样批次
      </button>
      <label>
        选择抽样批次
        <select
          aria-label="选择抽样批次"
          value={detail?.batch.id ?? ""}
          disabled={busy}
          onChange={(e) => {
            if (e.target.value) void act(() => load(e.target.value));
          }}
        >
          <option value="">请选择</option>
          {batches.map((b) => (
            <option key={b.id} value={b.id}>
              {new Date(b.created_at).toLocaleString("zh-CN")} ·{" "}
              {b.purpose === "acceptance" ? "验收" : "开发"} · {b.seed}
            </option>
          ))}
        </select>
      </label>
      <details>
        <summary>建立固定样本</summary>
        <EditorForm
          fields={[
            { key: "seed", label: "抽样种子（用于复现样本顺序）" },
            {
              key: "purpose",
              label: "样本用途",
              options: [
                ["development", "开发调试"],
                ["acceptance", "独立验收"],
              ],
            },
            {
              key: "target_count",
              label: "目标配对数（1–100）",
              initial: "30",
            },
          ]}
          label="固定抽样"
          disabled={busy || !actor.trim()}
          submit={(v) =>
            act(async () => {
              const created = await request<S["ClusterAuditBatchView"]>(
                "/editorial/cluster-audits",
                { ...v, actor, target_count: Number(v.target_count) },
              );
              setBatches(
                await request<S["ClusterAuditBatchView"][]>(
                  "/editorial/cluster-audits",
                ),
              );
              await load(created.id);
            })
          }
        />
      </details>
      {detail && (
        <>
          <p>
            本批 {detail.pairs.length} / 目标 {detail.batch.target_count} 对 ·
            抽样范围 {detail.batch.considered_events} /{" "}
            {detail.batch.population_events} 个事件
          </p>
          {detail.pairs.length < detail.batch.target_count && (
            <p className="muted">样本不足，已保留全部可用配对。</p>
          )}
          <AuditMetrics title="首次盲判" metrics={detail.blind_metrics} />
          <AuditMetrics title="最新判断（含更正）" metrics={detail.metrics} />
          <details>
            <summary>统计口径与限制</summary>
            {detail.limitations.map((t) => (
              <p key={t} className="muted">
                {t}
              </p>
            ))}
          </details>
          {pair && (
            <>
              <div className="validation-actions">
                <button
                  disabled={busy || position === 0}
                  onClick={() => setPosition(position - 1)}
                >
                  上一对
                </button>
                <span>
                  第 {position + 1} / {detail.pairs.length} 对
                </span>
                <button
                  disabled={busy || position + 1 === detail.pairs.length}
                  onClick={() => setPosition(position + 1)}
                >
                  下一对
                </button>
              </div>
              <div className="editorial-gates">
                {(["left", "right"] as const).map((side) => {
                  const frozen = pair.snapshot[side] as FrozenSide;
                  return (
                    <div className="session-card" key={side}>
                      <h3>
                        {side === "left" ? "材料组 A" : "材料组 B"} ·{" "}
                        {frozen.event.title}
                      </h3>
                      <p>
                        {frozen.event.subject} · {frozen.event.action} ·{" "}
                        {frozen.event.object}
                      </p>
                      <p className="muted">
                        {frozen.event.scope} · 版本{" "}
                        {frozen.event.event_version ?? "未知"} · 时间{" "}
                        {frozen.event.happened_at ?? "未知"}
                      </p>
                      {!frozen.materials.length && (
                        <p>抽样时未关联原文，只能记录无法判断。</p>
                      )}
                      {frozen.materials.map((m) => (
                        <div key={m.version_id}>
                          <p>
                            {m.source} · {m.title}
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
                          {m.paragraphs.map((p) => (
                            <p className="paragraph" key={p.id}>
                              {p.id} · {p.text}
                            </p>
                          ))}
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
              <AuditLabel
                key={`${pair.id}:${pair.labels.length}`}
                pair={pair}
                actor={actor}
                busy={busy}
                submit={(values) =>
                  act(async () => {
                    await request(
                      `/editorial/cluster-audits/${detail.batch.id}/pairs/${pair.id}/labels`,
                      {
                        ...values,
                        actor,
                        expected_revision: pair.labels.at(-1)?.revision ?? 0,
                      },
                    );
                    setDetail(
                      await request<S["AuditDetail"]>(
                        `/editorial/cluster-audits/${detail.batch.id}`,
                      ),
                    );
                  })
                }
              />
              {pair.prediction ? (
                <div className="session-card">
                  <h3>
                    抽样时的机器结果 ·{" "}
                    {verdicts[String(pair.prediction.suggestion)]}
                  </h3>
                  <p>规则版本：{detail.batch.method}</p>
                  {[
                    ...((pair.prediction.reasons as string[]) ?? []),
                    ...((pair.prediction.conflicts as string[]) ?? []),
                  ].map((r, i) => (
                    <p key={i}>{r}</p>
                  ))}
                </div>
              ) : (
                <p className="muted">提交首次判断后显示机器结果。</p>
              )}
              {pair.labels.map((l) => (
                <div className="session-card" key={l.id}>
                  <strong>
                    判断 {l.revision} · {verdicts[l.verdict]}
                  </strong>
                  <p>
                    {l.actor} · {new Date(l.created_at).toLocaleString("zh-CN")}
                  </p>
                  <p>{l.reason}</p>
                  {l.revision > 1 && (
                    <p className="muted">
                      查看机器结果后的更正，原始盲判仍保留。
                    </p>
                  )}
                </div>
              ))}
            </>
          )}
        </>
      )}
    </details>
  );
}

function AuditMetrics({
  title,
  metrics: m,
}: {
  title: string;
  metrics: Record<string, unknown>;
}) {
  const percent = (v: unknown) =>
    typeof v === "number" ? `${(v * 100).toFixed(1)}%` : "暂无分母";
  return (
    <p>
      {title}：已标注 {String(m.reviewed)} · 错合 {String(m.wrong_merge)} · 错拆{" "}
      {String(m.wrong_split)} · 机器未明确判断 {String(m.machine_abstained)} ·
      同事件未获正向建议 {String(m.same_without_positive_suggestion)}
      <br />
      明确判断错误率 {percent(m.error_rate)}（分母 {String(m.evaluated)}） ·
      明确判断覆盖率 {percent(m.decision_coverage)}
    </p>
  );
}

function AuditLabel({
  pair,
  actor,
  busy,
  submit,
}: {
  pair: S["PairView"];
  actor: string;
  busy: boolean;
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
        我已核对两侧原文与事件边界
      </label>
      <EditorForm
        fields={[
          {
            key: "verdict",
            label: "人工配对判断",
            options: [
              ["uncertain", "无法判断"],
              ["same", "同一事件"],
              ["different", "不同事件"],
            ],
          },
          { key: "reason", label: "配对判断依据", multiline: true },
        ]}
        label={pair.labels.length ? "保存判断更正" : "保存首次盲判"}
        disabled={busy || !actor.trim()}
        submit={(v) => submit({ ...v, original_checked: checked })}
      />
    </div>
  );
}
