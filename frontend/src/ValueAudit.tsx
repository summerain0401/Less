import { useState } from "react";
import { EditorForm, request } from "./editorialForms";
type Sample = {
  run_id: string;
  input: {
    events: {
      title: string;
      materials: {
        version_id: string;
        title: string;
        url: string;
        paragraphs: { id: string; text: string }[];
      }[];
    }[];
  };
  proposal: Record<string, unknown> | null;
  reviews: {
    revision: number;
    actor: string;
    verdict: string;
    important_reason: string;
    useful_reason: string;
  }[];
};
type Batch = {
  id: number;
  pool: string;
  target_count: number;
  population: number;
  samples: Sample[];
  blind_counts: Record<string, number>;
  latest_counts: Record<string, number>;
  limitations: string;
};
export function ValueAudit({ actor }: { actor: string }) {
  const [batches, setBatches] = useState<
    { id: number; seed: string; pool: string; sample_count: number }[]
  >([]);
  const [batch, setBatch] = useState<Batch | null>(null);
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
  async function load(id: number) {
    setBatch(await request<Batch>(`/assist/audits/${id}`));
    setPosition(0);
  }
  const sample = batch?.samples[position];
  const names: Record<string, string> = {
    value: "具备价值",
    no_value: "价值不足",
    uncertain: "无法判断",
    reviewed: "已复核",
  };
  return (
    <details className="work-panel">
      <summary>候选认可与机器漏选审计</summary>
      <p className="muted">
        固定抽取机器候选或排除项；先对照原文判断价值，提交后再看机器理由。不会据审计结果直接批准事件。
      </p>
      {error && <p role="alert">{error}</p>}
      <button
        disabled={busy}
        onClick={() =>
          void act(async () => setBatches(await request("/assist/audits")))
        }
      >
        读取价值审计批次
      </button>
      <label>
        价值审计批次
        <select
          value={batch?.id ?? ""}
          disabled={busy}
          onChange={(e) => {
            if (e.target.value) void act(() => load(Number(e.target.value)));
          }}
        >
          <option value="">请选择</option>
          {batches.map((b) => (
            <option key={b.id} value={b.id}>
              {b.seed} · {b.pool === "excluded" ? "排除项" : "候选"} ·{" "}
              {b.sample_count} 条
            </option>
          ))}
        </select>
      </label>
      <EditorForm
        fields={[
          { key: "seed", label: "价值审计抽样种子" },
          {
            key: "pool",
            label: "审计范围",
            options: [
              ["excluded", "机器排除项"],
              ["candidate", "机器候选"],
            ],
          },
          { key: "target_count", label: "目标事件数", initial: "20" },
        ]}
        label="固定价值抽样"
        disabled={busy || !actor.trim()}
        submit={(v) =>
          act(async () => {
            const created = await request<{ id: number }>("/assist/audits", {
              ...v,
              actor,
              target_count: Number(v.target_count),
            });
            setBatches(await request("/assist/audits"));
            await load(created.id);
          })
        }
      />
      {batch && (
        <>
          <p>
            {batch.samples.length} / 目标 {batch.target_count} 条 · 总体{" "}
            {batch.population} 条
            {batch.samples.length < batch.target_count
              ? " · 样本不足，已全查可用项"
              : ""}
          </p>
          <p className="muted">{batch.limitations}</p>
          {[
            ["首次盲判", batch.blind_counts],
            ["最新判断", batch.latest_counts],
          ].map(([title, counts]) => (
            <p key={String(title)}>
              {String(title)}：
              {Object.entries(counts as Record<string, number>)
                .map(([k, n]) => `${names[k] ?? k} ${n}`)
                .join(" · ")}
            </p>
          ))}
        </>
      )}
      {batch && sample && (
        <>
          <div className="validation-actions">
            <button
              disabled={busy || position === 0}
              onClick={() => setPosition(position - 1)}
            >
              上一项审计
            </button>
            <span>第 {position + 1} 项</span>
            <button
              disabled={busy || position + 1 === batch.samples.length}
              onClick={() => setPosition(position + 1)}
            >
              下一项审计
            </button>
          </div>
          {sample.input.events.map((event, i) => (
            <div key={i}>
              <h3>{event.title}</h3>
              {event.materials.map((m) => (
                <details key={m.version_id} open>
                  <summary>{m.title}</summary>
                  <a href={m.url} target="_blank" rel="noreferrer">
                    原文 ↗
                  </a>
                  {m.paragraphs.map((p) => (
                    <p className="paragraph" key={p.id}>
                      {p.id} · {p.text}
                    </p>
                  ))}
                </details>
              ))}
            </div>
          ))}
          <Judge
            key={`${sample.run_id}:${sample.reviews.length}`}
            disabled={busy || !actor.trim()}
            submit={(v) =>
              act(async () => {
                await request(`/assist/audits/${batch.id}/reviews`, {
                  ...v,
                  actor,
                  run_id: sample.run_id,
                  expected_revision: sample.reviews.length,
                });
                setBatch(await request<Batch>(`/assist/audits/${batch.id}`));
              })
            }
          />
          {sample.proposal ? (
            <div className="session-card">
              <h4>抽样时的机器理由</h4>
              <p>Important：{String(sample.proposal.important_reason)}</p>
              <p>Useful：{String(sample.proposal.useful_reason)}</p>
            </div>
          ) : (
            <p className="muted">提交首次判断后显示机器理由。</p>
          )}
          {sample.reviews.map((r) => (
            <p key={r.revision}>
              判断 {r.revision} · {r.actor} · {names[r.verdict]}：
              {r.important_reason}；{r.useful_reason}
            </p>
          ))}
        </>
      )}
    </details>
  );
}
function Judge({
  disabled,
  submit,
}: {
  disabled: boolean;
  submit: (v: Record<string, unknown>) => Promise<void>;
}) {
  const [checked, setChecked] = useState(false);
  return (
    <>
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => setChecked(e.target.checked)}
        />
        已对照原文独立判断价值
      </label>
      <EditorForm
        fields={[
          {
            key: "verdict",
            label: "人工价值审计",
            options: [
              ["uncertain", "无法判断"],
              ["value", "Important 或 Useful 成立"],
              ["no_value", "两条价值路径均不足"],
            ],
          },
          { key: "important_reason", label: "审计重要性理由", multiline: true },
          { key: "useful_reason", label: "审计实用性理由", multiline: true },
        ]}
        label="保存价值盲判"
        disabled={disabled}
        submit={(v) => submit({ ...v, original_checked: checked })}
      />
    </>
  );
}
