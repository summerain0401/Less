import { useState } from "react";
import type { components } from "./api.generated";

export type S = components["schemas"];
export type EventDetail = S["EventDetail"];
export type Field = {
  key: string;
  label: string;
  options?: [string, string][];
  optional?: boolean;
  multiline?: boolean;
  initial?: string;
};
export const states: Record<string, string> = {
  pending: "待判断",
  passed: "通过",
  rejected: "驳回",
  selected: "入选",
  deferred: "待核实",
  evidence_only: "仅存证",
  observe: "继续观察",
  unchecked: "未核验",
  verified: "已核验",
  needs_review: "需复核",
  supporting: "支持",
  counter: "反面 / 限制",
  context: "背景",
  fact_candidate: "待核验事实",
  reported_claim: "有归属的主张",
  interpretation: "解释 / 推断",
};
export const reason: Field = {
  key: "reason",
  label: "本次操作依据",
  multiline: true,
};
export const skeleton: Field[] = [
  { key: "title", label: "事件标题" },
  { key: "subject", label: "主体 · 谁" },
  { key: "action", label: "动作 · 做了什么" },
  { key: "object", label: "对象 · 针对什么" },
  { key: "event_version", label: "产品版本或范围标识（可空）", optional: true },
  { key: "scope", label: "适用范围、时间与已知限制", multiline: true },
];

export async function request<T>(
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
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string" ? data.detail : "请检查必填项与内容格式",
    );
  return data;
}

export function EditorForm({
  fields,
  label,
  disabled,
  submit,
}: {
  fields: Field[];
  label: string;
  disabled: boolean;
  submit: (values: Record<string, string>) => Promise<void>;
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      fields.map((f) => [f.key, f.initial ?? f.options?.[0]?.[0] ?? ""]),
    ),
  );
  return (
    <form
      className="validation-form"
      onSubmit={(e) => {
        e.preventDefault();
        void submit(values);
      }}
    >
      {fields.map((f) => (
        <label key={f.key}>
          {f.label}
          {f.options ? (
            <select
              aria-label={f.label}
              value={values[f.key]}
              onChange={(e) =>
                setValues({ ...values, [f.key]: e.target.value })
              }
            >
              {f.options.map(([value, label]) => (
                <option value={value} key={value}>
                  {label}
                </option>
              ))}
            </select>
          ) : f.multiline ? (
            <textarea
              aria-label={f.label}
              required={!f.optional}
              value={values[f.key]}
              onChange={(e) =>
                setValues({ ...values, [f.key]: e.target.value })
              }
            />
          ) : (
            <input
              aria-label={f.label}
              required={!f.optional}
              value={values[f.key]}
              onChange={(e) =>
                setValues({ ...values, [f.key]: e.target.value })
              }
            />
          )}
        </label>
      ))}
      <button
        disabled={
          disabled || fields.some((f) => !f.optional && !values[f.key]?.trim())
        }
        type="submit"
      >
        {label}
      </button>
    </form>
  );
}
