import React, { useEffect, useState } from "react";

type GuideSection = {
  id: string;
  label: string;
  number: string;
};

const sections: GuideSection[] = [
  { id: "purpose", label: "系统使命", number: "01" },
  { id: "workflow", label: "工作流程", number: "02" },
  { id: "model", label: "内容模型", number: "03" },
  { id: "judgment", label: "编辑判断", number: "04" },
  { id: "workspaces", label: "工作区指南", number: "05" },
  { id: "architecture", label: "技术架构", number: "06" },
  { id: "boundaries", label: "边界与状态", number: "07" },
];

const Chevron = () => (
  <svg viewBox="0 0 20 20" aria-hidden="true">
    <path d="m7 5 5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);

export function SystemGuide({ onNavigate }: { onNavigate: (tab: string) => void }) {
  const [active, setActive] = useState("purpose");

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible) setActive(visible.target.id);
      },
      { rootMargin: "-18% 0px -62%", threshold: [0.05, 0.35] },
    );
    sections.forEach(({ id }) => {
      const element = document.getElementById(id);
      if (element) observer.observe(element);
    });
    return () => observer.disconnect();
  }, []);

  const openWorkspace = (tab: string) => {
    window.history.replaceState(null, "", window.location.pathname);
    onNavigate(tab);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="guide-shell">
      <section className="guide-hero" aria-labelledby="guide-title">
        <div className="guide-hero-copy">
          <div className="guide-kicker"><span /> LESS / SYSTEM MANUAL</div>
          <h1 id="guide-title">少读一点，<br />知道更多。</h1>
          <p className="guide-intro">
            Less 是一套面向 AI 行业的本地内容与认知引擎。它把分散的原始材料，
            逐步整理成可核查的事件、简报与长期判断，同时保留每一步的证据和人工决定。
          </p>
          <div className="guide-hero-actions">
            <button onClick={() => document.getElementById("workflow")?.scrollIntoView({ behavior: "smooth" })}>
              了解工作方式 <span>↓</span>
            </button>
            <button className="quiet" onClick={() => openWorkspace("items")}>进入工作台</button>
          </div>
        </div>
        <div className="guide-hero-mark" aria-hidden="true">
          <span>READ</span>
          <strong>LESS</strong>
          <i />
          <span>KNOW</span>
          <strong>MORE</strong>
        </div>
        <div className="guide-hero-foot">
          <span>内容引擎 · 编辑工作台 · 可追溯知识</span>
          <span>PHASE 1 / 2026</span>
        </div>
      </section>

      <div className="guide-layout">
        <aside className="guide-toc" aria-label="说明书目录">
          <div>本页目录</div>
          {sections.map((section) => (
            <a key={section.id} className={active === section.id ? "active" : ""} href={`#${section.id}`}>
              <small>{section.number}</small><span>{section.label}</span>
            </a>
          ))}
        </aside>

        <div className="guide-content">
          <section id="purpose" className="guide-section guide-purpose">
            <div className="guide-section-label">01 / WHY LESS</div>
            <div className="guide-lead-grid">
              <h2>信息很多，<br />理解仍然稀缺。</h2>
              <div>
                <p className="guide-lede">Less 解决的不是“找不到资讯”，而是很难持续判断什么值得看、它意味着什么，以及我们的判断是否经得起新证据。</p>
                <p>系统首先服务于编辑工作：缩小观察范围，保存原始依据，把相同事件的重复报道归拢起来，再用简短、可回溯的内容交付真正的新信息。</p>
              </div>
            </div>
            <div className="guide-principles">
              <article><b>01</b><h3>选择，而非堆积</h3><p>内容必须满足 Important 或 Useful，数量从来不是目标。</p></article>
              <article><b>02</b><h3>证据先于结论</h3><p>每个关键陈述回到原文；不确定、限制和反证同样被保存。</p></article>
              <article><b>03</b><h3>机器辅助，人来判断</h3><p>AI 负责发现和草拟，人负责取舍、核验、批准与更正。</p></article>
            </div>
          </section>

          <section id="workflow" className="guide-section">
            <div className="guide-section-label">02 / HOW IT FLOWS</div>
            <div className="guide-heading-row"><h2>一条信息的旅程</h2><p>从外部来源到长期认知，每次转化都留下版本、依据和责任人。</p></div>
            <div className="guide-flow">
              {[
                ["SOURCE", "观察来源", "持续检查被选择的官方、研究、开发者与媒体节点。"],
                ["ITEM", "保存材料", "保留正文快照、发布时间、出处和不可变版本。"],
                ["EVENT", "还原事件", "把多篇相关材料聚为同一件事，拆开事实与主张。"],
                ["BRIEF", "形成简报", "说明发生了什么、为何重要，以及仍有哪些未知。"],
                ["SIGNAL", "更新判断", "让可证伪的长期判断随支持或反对证据变化。"],
              ].map(([code, title, copy], index) => (
                <article key={code}>
                  <div className="guide-flow-index">{String(index + 1).padStart(2, "0")}</div>
                  <div><small>{code}</small><h3>{title}</h3><p>{copy}</p></div>
                  {index < 4 && <span className="guide-flow-line" />}
                </article>
              ))}
            </div>
            <div className="guide-callout"><span>核心原则</span><p>系统保存的不是一条从左到右、不可更改的流水线，而是一张能够从判断反查到原始材料的证据网络。</p></div>
          </section>

          <section id="model" className="guide-section">
            <div className="guide-section-label">03 / CONTENT MODEL</div>
            <div className="guide-heading-row"><h2>六类核心对象</h2><p>对象各自回答一个问题，避免把来源、事实、内容和判断混在一起。</p></div>
            <div className="guide-object-grid">
              {[
                ["S", "Source", "从哪里观察？", "具体的信息节点及其角色、权威性、偏向和健康状态。"],
                ["I", "Item", "原文说了什么？", "一篇文章、发布说明、论文或讨论，以及它的保存版本。"],
                ["E", "Event", "实际上发生了什么？", "由一份或多份材料共同描述的外部事件。"],
                ["B", "Brief", "这件事为何值得知道？", "面向读者的短内容，包含事实、意义、限制与来源。"],
                ["G", "Signal", "长期变化是什么？", "能够被后续证据支持、收窄、削弱或推翻的判断。"],
                ["↗", "Evidence", "凭什么这样判断？", "材料与陈述、事件或 Signal 之间可定位的关系。"],
              ].map(([symbol, title, question, copy]) => (
                <article key={title}><i>{symbol}</i><div><small>{question}</small><h3>{title}</h3><p>{copy}</p></div></article>
              ))}
            </div>
          </section>

          <section id="judgment" className="guide-section">
            <div className="guide-section-label">04 / EDITORIAL JUDGMENT</div>
            <div className="guide-heading-row"><h2>两道门，四个问题</h2><p>机器可以提出候选，但内容只有经过明确的人工作出决定，才会进入后续交付。</p></div>
            <div className="guide-gates">
              <article><small>GATE 01</small><h3>价值门</h3><strong>Important <em>OR</em> Useful</strong><p>它是否改变对重要趋势的理解？或者能否帮助目标读者作出更好的实际决策？满足其一才值得继续。</p></article>
              <div className="guide-gate-arrow"><Chevron /></div>
              <article><small>GATE 02</small><h3>质量门</h3><strong>Source <em>AND</em> Evidence</strong><p>来源是否适合支撑这类陈述？关键证据能否回到具体原文？两者都成立，内容才具备交付基础。</p></article>
            </div>
            <div className="guide-questions">
              {[["1", "发生了什么？"], ["2", "为什么重要或有用？"], ["3", "证据和边界在哪里？"], ["4", "它改变了什么判断？"]].map(([n, q]) => <div key={n}><span>{n}</span><p>{q}</p></div>)}
            </div>
          </section>

          <section id="workspaces" className="guide-section">
            <div className="guide-section-label">05 / WORKSPACE GUIDE</div>
            <div className="guide-heading-row"><h2>从哪里开始</h2><p>每个工作区对应内容生产中的一个清晰任务。</p></div>
            <div className="guide-workspaces">
              {[
                ["01", "原始材料", "查看保存正文、出处与结构化提取，逐项核对机器输出。", "items"],
                ["02", "来源管理", "检查来源状态、观察范围与采集健康，按需发起采集。", "sources"],
                ["03", "验收台", "用固定样本检验字段准确率，并记录真实人工工作量。", "validation"],
                ["04", "编辑收件箱", "整理 Event、Claim 与 Evidence，完成价值门和质量门。", "editorial"],
                ["05", "Brief 与 Today", "审核版本、内部发布每日精选，并在次日记录阅读价值。", "briefs"],
                ["06", "Signal", "维护可证伪假设、正反证据、检索记录与复评历史。", "signals"],
                ["07", "机器辅助", "查看聚类、初筛和草稿建议，通过盲审衡量真实帮助。", "assist"],
                ["08", "运行记录", "区分成功、失败、无更新和漏执行，追踪系统的真实过程。", "activity"],
              ].map(([number, title, copy, tab]) => (
                <button key={title} onClick={() => openWorkspace(tab)}>
                  <small>{number}</small><div><h3>{title}</h3><p>{copy}</p></div><Chevron />
                </button>
              ))}
            </div>
          </section>

          <section id="architecture" className="guide-section">
            <div className="guide-section-label">06 / UNDER THE HOOD</div>
            <div className="guide-heading-row"><h2>本地、可替换、可恢复</h2><p>首期采用模块化单体，把内容质量和运行可靠性放在基础设施复杂度之前。</p></div>
            <div className="guide-architecture">
              <div className="guide-arch-stack">
                <span>React 19 / TypeScript</span><i />
                <span>FastAPI / Pydantic</span><i />
                <span>Celery / Redis</span><i />
                <span>PostgreSQL / Alembic</span>
              </div>
              <div className="guide-arch-notes">
                <article><b>版本化</b><p>原始快照、机器结果和人工判断分开保存，历史不会被重跑覆盖。</p></article>
                <article><b>可追溯</b><p>每条关键陈述都能回到段落；更改证据会让旧审核失效。</p></article>
                <article><b>有限自动化</b><p>AI 串行运行并受每日预算约束，异常会暂停而不是悄悄跳过。</p></article>
                <article><b>本地优先</b><p>应用、数据库和任务服务绑定本机，首期不建设公网账号系统。</p></article>
              </div>
            </div>
          </section>

          <section id="boundaries" className="guide-section guide-boundaries">
            <div className="guide-section-label">07 / SCOPE & STATUS</div>
            <div className="guide-heading-row"><h2>系统已经能做什么</h2><p>工程能力与真实内容验证分开记录。功能存在，不代表内容质量已经得到证明。</p></div>
            <div className="guide-status-grid">
              <article><span>已实现</span><ul><li>来源采集与不可变原文版本</li><li>结构化提取与逐字段验收</li><li>Event / Evidence 编辑闭环</li><li>Brief、Today 与阅读反馈</li><li>Signal、反证和复评历史</li></ul></article>
              <article><span>正在验证</span><ul><li>连续运行的稳定性</li><li>关键字段的人工准确率</li><li>机器建议的真实编辑价值</li><li>每日内容的阅读价值</li><li>Signal 的长期认知增量</li></ul></article>
            </div>
            <div className="guide-boundary-note"><div>!</div><p><strong>请记住：</strong>结构化提取不等于事实核验，机器标签不等于编辑判断，保存版本不等于发布批准。任何发布和 Signal 状态变化都需要明确的人工决定。</p></div>
          </section>

          <footer className="guide-footer">
            <div><strong>Less</strong><span>Read less. Know more.</span></div>
            <button onClick={() => openWorkspace("items")}>打开编辑工作台 <Chevron /></button>
          </footer>
        </div>
      </div>
    </div>
  );
}
