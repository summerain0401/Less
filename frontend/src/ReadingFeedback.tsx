import { useEffect, useState } from "react";
import { EditorForm, request } from "./editorialForms";
import type { S } from "./editorialForms";
export function ReadingFeedback({
  detail,
  actor,
  disabled,
}: {
  detail: S["BriefDetailView"];
  actor: string;
  disabled: boolean;
}) {
  const [records, setRecords] = useState<S["ReadingView"][]>([]);
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const path = `/briefs/${detail.brief.id}/reading-feedback`;
  useEffect(() => {
    let active = true;
    request<S["ReadingView"][]>(path)
      .then((v) => {
        if (active) setRecords(v);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [path]);
  return (
    <details className="work-panel">
      <summary>次日阅读反馈</summary>
      <p className="muted">
        发布次日或之后实际复读，再判断是否仍愿意看；晚于次日的反馈单列。再次提交保留历史，统计使用每位读者对该版本的最新次日反馈。
      </p>
      {error && <p role="alert">{error}</p>}
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => setChecked(e.target.checked)}
        />
        我已实际复读所选已发布版本
      </label>
      <EditorForm
        fields={[
          {
            key: "version_id",
            label: "实际复读版本",
            options: detail.versions.map((v) => [
              v.id,
              `版本 ${v.revision} · ${String(v.content.title)}`,
            ]),
          },
          {
            key: "would_read_again",
            label: "是否仍愿意看",
            options: [
              ["false", "不愿意"],
              ["true", "愿意"],
            ],
          },
          { key: "reason", label: "实际阅读价值与原因", multiline: true },
        ]}
        label="记录阅读反馈"
        disabled={disabled || busy || !checked}
        submit={async (v) => {
          setBusy(true);
          setError("");
          try {
            await request(path, {
              ...v,
              actor,
              read_original: checked,
              would_read_again: v.would_read_again === "true",
            });
            setRecords(await request<S["ReadingView"][]>(path));
            setChecked(false);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      />
      {records.map((r) => (
        <p key={r.id}>
          {r.actor} · {r.next_day ? "次日" : "后续复读"} ·{" "}
          {r.would_read_again ? "仍愿意看" : "不愿意看"}：{r.reason}
        </p>
      ))}
    </details>
  );
}
