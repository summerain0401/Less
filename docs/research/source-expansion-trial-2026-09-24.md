# 来源扩充试扫记录 · 2026-09-24

这份记录用于校准首选来源，不是 Brief，也不改变自动采集范围。试扫以 2026-09-17—24 的近期内容为主，结合仓库现有的 10 条 Brief 去重；少量较早页面用于判断入口的活跃度和用途。

## 宽泛近期扫描

查看了 Epoch AI、Artificial Analysis、英国 AI Security Institute、Hugging Face Daily Papers、Anthropic Engineering、Shopify Engineering、Exploring Generative AI、Interconnects 等入口，并核对了相关原文。

| 线索与原文 | 判断 |
| --- | --- |
| [Epoch AI：The plunging price of thought](https://epoch.ai/publications/the-plunging-price-of-thought)，9 月 22 日 | 新增且与已存单次模型价格 Brief 不重复。其固定能力成本测量可作为 Frontier / Signals 的 Important 候选；概括降价幅度时须保留基准任务和测量方法。 |
| [Nathan Lambert：The current balance of power in open models](https://www.interconnects.ai/p/the-current-balance-of-power-in-open)，9 月 21 日 | 新增 Voices / Signals 候选，需把作者判断与所引数据分开；其 X 帖与文章重复，只算一条线索。 |
| [Hugging Face Daily Papers](https://huggingface.co/papers) 上的 [Schrödinger's Code Repository 论文](https://arxiv.org/abs/2609.27891) | 发现页 9 月 24 日列出，论文原页标注 8 月 21 日提交。发现日期不能当作研究发表日期。 |

英国 AI Security Institute、Exploring Generative AI 在此次窗口内没有更近的合格材料；仍保留其独立评估与工程实践入口，不按每日更新量设门槛。

## AI Coding / Agents 专题扫描

查看了 Shopify Engineering、Anthropic Engineering、Claude Developers、OpenCompass、Hugging Face Daily Papers，以及 Tibo、Boris Cherny、Simon Willison 等人的相关帖文。

| 线索与原文 | 判断 |
| --- | --- |
| [Boris Cherny 原帖](https://x.com/bcherny/status/2102543349102338309)与[后续补充](https://x.com/bcherny/status/2102898067133595992)，9 月 23—24 日 | 新增且不重复的 Useful 候选：作者称团队以 Lean / TLA+ 检查 Claude Agent SDK 的困难部分，并报告 16 个 PR；后续明确不是对整个 SDK 的形式化验证。PR 数量尚未逐一独立核对，发表时须注明是作者自述。 |
| [Claude Developers：How we made Claude.ai faster](https://claude.dev/blog/how-we-made-claude-ai-faster/)，9 月 23 日 | 新增工程实践线索；原文有具体方法和条件。Anthropic Engineering 索引未覆盖这篇近期文章，因此将 Claude Developers 作为同一首选节点的补充入口。 |
| [JitMem 论文](https://arxiv.org/abs/2609.27334)，9 月 23 日 | Hugging Face 发现、原论文核对后的 Agents 研究线索；属于预印本，效果不应写成已独立复现。 |
| [Shopify Helix](https://shopify.engineering/helix)；Tibo 的 GPT-6 Sol / Luna 帖文 | 与现有 Brief 重复，跳过。Tibo 的 DevDay 预告尚未构成已发布的产品事实。 |

OpenCompass 在试扫窗口内无新的相关发布。Simon Willison 的 X 内容可供发现直接实验，但跨平台重复时以完整原文为主。Tibo 和 Boris 的账号分别保留作为 Codex、Claude Code 的第一手入口；不因预告或个人实验直接认定产品效果。

## 社媒可访问性与核验成本

直接通过网页检索工具打开五个 X 账号时均遇到访问限制；浏览器能读取当时公开的个人页及具体文字帖，但个人页只显示少量近期内容，并有登录遮挡，媒体内容未能完整核查。逐帖核验需要额外打开原帖、上下文、作者给出的链接与对应文档；比直接读取工程文章成本高。完整帖文或证据链不可读时，只记录为线索。此次没有因社媒线索单独写入 Brief。

结论：保留本轮新增入口；优先按主题检索低频站点，社媒账号只用于补充原作者信息。继续以 Important / Useful 和可核验性筛选，不设来源或 Brief 数量配额。
