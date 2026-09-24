import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import type { Brief, BriefDraft, BriefFields, Today, Topic } from "./types";
import "./style.css";

type Tab = "today" | "topics" | "manage";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const detail = data.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((item) => item.msg).join("；")
          : `请求失败 (${response.status})`;
    throw new Error(message);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

const jsonRequest = (method: "POST" | "PUT", body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const shanghaiToday = () =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());

const displayDate = (value: string | null | undefined) => {
  if (!value) return "日期未知";
  if (value.length === 10) return value;
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
};

function App() {
  const [tab, setTab] = useState<Tab>("today");
  const [selected, setSelected] = useState<Brief | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const navigate = (next: Tab) => {
    setTab(next);
    setSelected(null);
  };

  return (
    <div className="app-shell">
      <header className="site-header">
        <button className="brand" onClick={() => navigate("today")}>
          Less <span>Read less. Know more.</span>
        </button>
        <nav aria-label="主导航">
          {([
            ["today", "Today"],
            ["topics", "Topics"],
            ["manage", "管理"],
          ] as [Tab, string][]).map(([id, label]) => (
            <button
              key={id}
              className={tab === id ? "active" : ""}
              onClick={() => navigate(id)}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>
      <main>
        {selected ? (
          <BriefDetail brief={selected} onBack={() => setSelected(null)} />
        ) : tab === "today" ? (
          <TodayPage refreshKey={refreshKey} onOpen={setSelected} />
        ) : tab === "topics" ? (
          <TopicsPage refreshKey={refreshKey} onOpen={setSelected} />
        ) : (
          <ManagePage
            refreshKey={refreshKey}
            onChanged={() => setRefreshKey((value) => value + 1)}
            onOpen={setSelected}
          />
        )}
      </main>
      <footer>Less · 原始来源优先 · 事实与判断分开</footer>
    </div>
  );
}

function PageIntro({ eyebrow, title, children }: { eyebrow: string; title: string; children: string }) {
  return (
    <div className="page-intro">
      <span>{eyebrow}</span>
      <h1>{title}</h1>
      <p>{children}</p>
    </div>
  );
}

function TodayPage({ refreshKey, onOpen }: { refreshKey: number; onOpen: (brief: Brief) => void }) {
  const [day, setDay] = useState(shanghaiToday);
  const [today, setToday] = useState<Today | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setError("");
    api<Today>(`/today?day=${day}`)
      .then((result) => active && setToday(result))
      .catch((reason) => active && setError(reason.message));
    return () => {
      active = false;
    };
  }, [day, refreshKey]);

  return (
    <>
      <PageIntro eyebrow="TODAY" title="今天，有什么值得知道？">
        少量、可信、可以追溯。来源日期和保留日期分别呈现，不把旧资料包装成今天的新闻。
      </PageIntro>
      <div className="toolbar">
        <label>
          阅读日期
          <input aria-label="阅读日期" type="date" value={day} onChange={(e) => setDay(e.target.value)} />
        </label>
        <span>{today ? `${today.entries.length} 条 Brief` : "读取中…"}</span>
      </div>
      {error && <Notice error>{error}</Notice>}
      {today && today.entries.length === 0 && (
        <div className="empty-state">
          <h2>这一天没有值得保留的新内容</h2>
          <p>空白也是编辑判断的一部分，不为更新频率降低标准。</p>
        </div>
      )}
      <div className="brief-grid">
        {today?.entries.map((brief) => <BriefCard key={brief.id} brief={brief} onOpen={onOpen} />)}
      </div>
    </>
  );
}

function BriefCard({ brief, onOpen }: { brief: Brief; onOpen: (brief: Brief) => void }) {
  return (
    <article className="brief-card">
      <div className="card-meta">
        <span>{brief.sources.find((source) => source.primary)?.name ?? brief.sources[0]?.name}</span>
        <time>{displayDate(brief.published_at)}</time>
      </div>
      <h2>{brief.title}</h2>
      <p className="what fact-body">{brief.what_happened}</p>
      <div className="why">
        <span>为什么值得关注</span>
        <p>{brief.why_it_matters}</p>
      </div>
      <div className="card-footer">
        <div className="tags">{brief.topics.map((topic) => <span key={topic}>{topic}</span>)}</div>
        <button onClick={() => onOpen(brief)}>阅读全文</button>
      </div>
    </article>
  );
}

function BriefDetail({ brief, onBack }: { brief: Brief; onBack: () => void }) {
  return (
    <article className="detail-page">
      <button className="back" onClick={onBack}>← 返回</button>
      <div className="detail-meta">
        <span>{brief.important ? "Important" : "Useful"}{brief.important && brief.useful ? " · Useful" : ""}</span>
        <span>{brief.confidence === "high" ? "高核验把握" : "中等核验把握"}</span>
        <span>来源日期 {displayDate(brief.published_at)}</span>
      </div>
      <h1>{brief.title}</h1>
      <section>
        <h2>发生了什么</h2>
        <p className="fact-body">{brief.what_happened}</p>
      </section>
      <section>
        <h2>为什么值得关注</h2>
        <p>{brief.why_it_matters}</p>
      </section>
      {brief.our_take && (
        <section className="our-take">
          <h2>Less 怎么看</h2>
          <p>{brief.our_take}</p>
        </section>
      )}
      {brief.uncertainty && (
        <section className="uncertainty">
          <h2>限制与不确定性</h2>
          <p>{brief.uncertainty}</p>
        </section>
      )}
      <section>
        <h2>原始来源</h2>
        <div className="source-list">
          {brief.sources.map((source) => (
            <a key={source.url} href={source.url} target="_blank" rel="noreferrer">
              <strong>{source.name}</strong>
              <span>{source.primary ? "主要来源" : "补充来源"} · {displayDate(source.published_at)}</span>
              <b>打开原文 ↗</b>
            </a>
          ))}
        </div>
      </section>
      <div className="tags large">{brief.topics.map((topic) => <span key={topic}>{topic}</span>)}</div>
      <p className="saved-at">保留于 {displayDate(brief.created_at)}{brief.updated_at ? ` · 更正于 ${displayDate(brief.updated_at)}` : ""}</p>
    </article>
  );
}

function TopicsPage({ refreshKey, onOpen }: { refreshKey: number; onOpen: (brief: Brief) => void }) {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [briefs, setBriefs] = useState<Brief[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([api<Topic[]>("/topics"), api<Brief[]>("/briefs")])
      .then(([nextTopics, nextBriefs]) => {
        if (!active) return;
        setTopics(nextTopics);
        setBriefs(nextBriefs);
      })
      .catch((reason) => active && setError(reason.message));
    return () => { active = false; };
  }, [refreshKey]);

  const shown = selected ? briefs.filter((brief) => brief.topics.includes(selected)) : briefs;
  return (
    <>
      <PageIntro eyebrow="TOPICS" title="从主题回看变化">
        主题来自已经保留的内容，不预建庞大的分类树。
      </PageIntro>
      {error && <Notice error>{error}</Notice>}
      {topics.length === 0 ? (
        <div className="empty-state"><h2>还没有主题</h2><p>保留第一条 Brief 后，主题会自然出现。</p></div>
      ) : (
        <div className="topic-pills">
          <button className={!selected ? "active" : ""} onClick={() => setSelected("")}>全部 · {briefs.length}</button>
          {topics.map((topic) => (
            <button key={topic.id} className={selected === topic.name ? "active" : ""} onClick={() => setSelected(topic.name)}>
              {topic.name} · {topic.brief_count}
            </button>
          ))}
        </div>
      )}
      <div className="brief-grid">{shown.map((brief) => <BriefCard key={brief.id} brief={brief} onOpen={onOpen} />)}</div>
    </>
  );
}

const example: BriefDraft = {
  id: "example-stable-id",
  title: "准确、简短的标题",
  published_at: null,
  topics: ["Agents"],
  important: true,
  useful: false,
  confidence: "high",
  sources: [{ name: "原始来源", url: "https://example.com/specific-page", type: "official_docs", primary: true, published_at: null }],
  what_happened: "主体及此前状态。此次具体新增、移除或改变了什么，以及有依据的结果。当前可用范围和影响理解的关键条件。",
  why_it_matters: "具体影响谁，以及为什么值得关注。",
  our_take: null,
  uncertainty: null,
};

function validateDraft(value: unknown, editing: boolean): string[] {
  if (!value || typeof value !== "object" || Array.isArray(value)) return ["顶层必须是 JSON 对象"];
  const draft = value as Record<string, unknown>;
  const errors: string[] = [];
  if (!editing && (typeof draft.id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(draft.id))) errors.push("id 必须是稳定的 URL 安全标识");
  for (const key of ["title", "what_happened", "why_it_matters"])
    if (typeof draft[key] !== "string" || !(draft[key] as string).trim()) errors.push(`缺少 ${key}`);
  if (!Array.isArray(draft.topics) || draft.topics.length === 0) errors.push("至少需要一个 topic");
  else if (draft.topics.some((topic) => typeof topic !== "string" || !topic.trim())) errors.push("topic 必须是非空文本");
  else if (new Set(draft.topics.map((topic) => topic.toLowerCase())).size !== draft.topics.length) errors.push("topic 不能重复");
  if (typeof draft.important !== "boolean" || typeof draft.useful !== "boolean") errors.push("important / useful 必须是布尔值");
  else if (!draft.important && !draft.useful) errors.push("important / useful 至少一项为 true");
  if (!["high", "medium"].includes(String(draft.confidence))) errors.push("正式保存只接受 high / medium confidence");
  if (draft.confidence === "medium" && !draft.uncertainty) errors.push("medium confidence 必须说明 uncertainty");
  if (!Array.isArray(draft.sources) || draft.sources.length === 0) errors.push("至少需要一个来源");
  else {
    const urls = new Set<string>();
    const sourceTypes = new Set(["official_docs", "release", "paper", "blog", "media", "other"]);
    for (const value of draft.sources) {
      if (!value || typeof value !== "object") { errors.push("来源必须是对象"); continue; }
      const source = value as Record<string, unknown>;
      if (typeof source.name !== "string" || !source.name.trim()) errors.push("来源缺少 name");
      if (!sourceTypes.has(String(source.type))) errors.push("来源 type 无效");
      try {
        const url = new URL(String(source.url));
        if (!["http:", "https:"].includes(url.protocol)) throw new Error();
        if (urls.has(url.href)) errors.push("来源链接不能重复");
        urls.add(url.href);
      } catch { errors.push("来源必须是有效的 http(s) 链接"); }
    }
    if (!draft.sources.some((source) => source && typeof source === "object" && (source as Record<string, unknown>).primary === true)) errors.push("至少标记一个主要来源");
  }
  return errors;
}

function validateInput(value: unknown, editing: boolean): string[] {
  if (editing) {
    if (Array.isArray(value)) return ["编辑时只能使用单个 Brief 对象"];
    return validateDraft(value, true);
  }
  const drafts = Array.isArray(value) ? value : [value];
  if (drafts.length === 0) return ["Brief 数组不能为空"];
  const errors = drafts.flatMap((draft, index) =>
    validateDraft(draft, false).map((error) => `第 ${index + 1} 条：${error}`),
  );
  const ids = new Set<string>();
  drafts.forEach((draft, index) => {
    if (!draft || typeof draft !== "object" || Array.isArray(draft)) return;
    const id = (draft as Record<string, unknown>).id;
    if (typeof id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(id)) return;
    if (ids.has(id)) errors.push(`第 ${index + 1} 条：id ${id} 在本次数组中重复`);
    ids.add(id);
  });
  return errors;
}

function stripMetadata(brief: Brief): BriefFields {
  const { id: _id, created_at: _created, updated_at: _updated, ...fields } = brief;
  return fields;
}

function ManagePage({ refreshKey, onChanged, onOpen }: { refreshKey: number; onChanged: () => void; onOpen: (brief: Brief) => void }) {
  const [text, setText] = useState(() => JSON.stringify(example, null, 2));
  const [parsed, setParsed] = useState<BriefDraft[] | BriefFields | null>([example]);
  const [errors, setErrors] = useState<string[]>([]);
  const [saveError, setSaveError] = useState("");
  const [briefs, setBriefs] = useState<Brief[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Brief[]>("/briefs").then(setBriefs).catch((reason) => setErrors([reason.message]));
  }, [refreshKey]);

  useEffect(() => {
    try {
      const value = JSON.parse(text);
      const nextErrors = validateInput(value, editingId !== null);
      setErrors(nextErrors);
      setParsed(nextErrors.length ? null : editingId ? value : Array.isArray(value) ? value : [value]);
    } catch {
      setErrors(["JSON 格式无效"]);
      setParsed(null);
    }
  }, [text, editingId]);

  const save = async () => {
    if (!parsed) return;
    setBusy(true);
    setNotice("");
    setSaveError("");
    try {
      if (editingId) {
        if (Array.isArray(parsed)) return;
        await api<Brief>(`/briefs/${editingId}`, jsonRequest("PUT", parsed));
        setNotice("更正已保存");
        setEditingId(null);
        setText(JSON.stringify(example, null, 2));
        onChanged();
      } else {
        if (!Array.isArray(parsed)) return;
        let saved = 0;
        try {
          for (const draft of parsed) {
            await api<Brief>("/briefs", jsonRequest("POST", draft));
            saved += 1;
          }
        } catch (reason) {
          setSaveError(`第 ${saved + 1} 条保存失败：${(reason as Error).message}`);
          if (saved > 0) {
            setNotice(`已保留 ${saved} 条；剩余 ${parsed.length - saved} 条草稿仍在输入框中。`);
            setText(JSON.stringify(parsed.slice(saved), null, 2));
            onChanged();
          }
          return;
        }
        setNotice(saved === 1 ? "Brief 已保留并进入今天" : `${saved} 条 Brief 已保留并进入今天`);
        setText(JSON.stringify(example, null, 2));
        onChanged();
      }
    } catch (reason) {
      setSaveError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (brief: Brief) => {
    if (!window.confirm(`确定移除“${brief.title}”？此操作不可撤销。`)) return;
    setBusy(true);
    try {
      await api(`/briefs/${brief.id}`, { method: "DELETE" });
      setNotice("Brief 已移除");
      onChanged();
    } catch (reason) {
      setErrors([(reason as Error).message]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageIntro eyebrow="MANAGE" title="只保留值得留下的内容">
        粘贴单条 Brief 对象或 Brief 对象数组，先检查内容本身，再决定保留或跳过。
      </PageIntro>
      {notice && <Notice>{notice}</Notice>}
      {saveError && <Notice error>{saveError}</Notice>}
      <div className="manage-layout">
        <section className="editor-panel">
          <div className="panel-heading">
            <h2>{editingId ? `更正 ${editingId}` : "导入 Brief 草稿"}</h2>
            <button disabled={busy} onClick={() => { setEditingId(null); setText(JSON.stringify(example, null, 2)); setSaveError(""); setNotice("草稿已跳过，未写入内容库"); }}>跳过 / 清空</button>
          </div>
          <label htmlFor="draft-json">Brief JSON</label>
          <textarea id="draft-json" aria-label="Brief JSON" value={text} onChange={(event) => { setText(event.target.value); setSaveError(""); setNotice(""); }} disabled={busy} spellCheck={false} />
          {errors.length > 0 ? (
            <div className="validation-errors" role="alert">{errors.map((error) => <p key={error}>{error}</p>)}</div>
          ) : (
            <p className="valid">{!editingId && Array.isArray(parsed) && parsed.length > 1 ? `${parsed.length} 条草稿结构检查通过，可以预览并保留。` : "结构检查通过，可以预览并保留。"}</p>
          )}
          <button className="primary-action" disabled={!parsed || busy} onClick={() => void save()}>
            {editingId ? "保存更正" : Array.isArray(parsed) && parsed.length > 1 ? `确认保留 ${parsed.length} 条` : "确认保留"}
          </button>
        </section>
        <section className="preview-panel">
          <h2>保存前预览{Array.isArray(parsed) ? ` · ${parsed.length} 条` : ""}</h2>
          {parsed ? Array.isArray(parsed) ? (
            <div className="preview-stack">{parsed.map((draft, index) => (
              <div className="preview-item" key={draft.id}>
                <p className="preview-index">第 {index + 1} 条 · {draft.id}</p>
                <DraftPreview draft={draft} />
              </div>
            ))}</div>
          ) : <DraftPreview draft={parsed} /> : <p className="muted">修正左侧问题后显示预览。</p>}
        </section>
      </div>
      <section className="saved-list">
        <h2>已保留 Brief</h2>
        {briefs.length === 0 && <p className="muted">内容库还是空的。</p>}
        {briefs.map((brief) => (
          <div key={brief.id} className="saved-row">
            <div><strong>{brief.title}</strong><span>{brief.id} · {displayDate(brief.created_at)}</span></div>
            <div>
              <button onClick={() => onOpen(brief)}>查看</button>
              <button disabled={busy} onClick={() => { setEditingId(brief.id); setText(JSON.stringify(stripMetadata(brief), null, 2)); setSaveError(""); setNotice(""); window.scrollTo({ top: 0, behavior: "smooth" }); }}>编辑</button>
              <button className="danger" disabled={busy} onClick={() => void remove(brief)}>删除</button>
            </div>
          </div>
        ))}
      </section>
    </>
  );
}

function DraftPreview({ draft }: { draft: BriefDraft | BriefFields }) {
  return (
    <div className="draft-preview">
      <div className="tags">{draft.topics.map((topic) => <span key={topic}>{topic}</span>)}</div>
      <h3>{draft.title}</h3>
      <small>{displayDate(draft.published_at)} · {draft.confidence}</small>
      <h4>发生了什么</h4><p className="fact-body">{draft.what_happened}</p>
      <h4>为什么值得关注</h4><p>{draft.why_it_matters}</p>
      {draft.our_take && <><h4>Less 怎么看</h4><p>{draft.our_take}</p></>}
      {draft.uncertainty && <><h4>限制</h4><p>{draft.uncertainty}</p></>}
      <h4>来源</h4>
      {draft.sources.map((source) => <p key={source.url}>{source.name} · {source.url}</p>)}
    </div>
  );
}

function Notice({ children, error = false }: { children: React.ReactNode; error?: boolean }) {
  return <div className={`notice ${error ? "error" : ""}`} role={error ? "alert" : "status"}>{children}</div>;
}

createRoot(document.getElementById("root")!).render(<App />);
