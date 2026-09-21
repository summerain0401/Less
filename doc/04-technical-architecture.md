# Less 技术架构与本地运行基线

| 文档信息 | 内容 |
|---|---|
| 版本 / 更新 | v0.1 / 2026-09-20 |
| 状态 | 技术选型已确认；采集、编辑、Brief、Signal 和机器辅助工作区已实现，真实内容验收进行中 |
| 维护角色 | 实施负责人 |
| 依据 | [产品蓝图](01-product-blueprint.md)、[编辑手册](02-editorial-handbook.md)、[MVP](03-phase-1-content-engine-mvp.md) |

## 1. 已确定的技术栈

| 层面 | 技术 |
|---|---|
| 后端 | Python 3.12、FastAPI、Pydantic |
| 数据库 / 迁移 | PostgreSQL 17、SQLAlchemy 2、Alembic |
| 前端 | React 19、TypeScript、Vite |
| 采集 | HTTPX、feedparser、Trafilatura；短 Feed 正文使用 HTML 文本提取补充 |
| 后台任务 | Celery、Redis 7、单个 Celery Beat |
| AI | 可替换执行器接口；首个实现为 Codex CLI |
| 环境与测试 | uv / uv.lock、npm / package-lock.json、pytest、Playwright |
| 部署 | 本地单仓库、模块化单体；Compose 运行 PostgreSQL 和 Redis |

API、前端、Worker 和 Beat 在宿主机运行。Worker 使用 `solo`、并发 1。数据库锁额外确保多 Worker 误启动时仍只有一个 AI 提取执行。服务及基础设施均绑定回环地址，不建设公网账号系统。

## 2. 数据流与接口

```text
Source Registry → 持久化采集计划 → Worker → 原文快照 + Item / ItemVersion
                                              ↓
                                 NormalizeRun → Codex CLI
                                              ↓
                                 Schema / 原文引用校验
                                              ↓
                                 原文对照 → HumanReview
```

后端提供 `/api/sources`、`/api/checks`、`/api/items`、`/api/versions/{id}`、`/api/runs` 和 `/api/overview`。采集与 Normalize 请求先落数据库，再由调度器派发。Redis 负责消息传递，数据库保存工作状态，因此丢失队列消息后仍可重新派发。

前端使用 OpenAPI 生成的类型。界面包含原始材料、来源管理、运行记录和原文/提取对照。源文以纯文本显示，保存快照也以文本响应，避免把外部 HTML 作为应用页面执行。

业务数据与模型结果分开：

- Source 记录具体节点、角色、Topics、Coverage、依据、偏向和接入健康。
- Item 按来源及规范化 URL 唯一；ItemVersion 由正文和相关元数据的内容哈希区分。
- SourceCheck 固定计划槽及首次条目批次，记录重试、错误、抓取数量和本轮未处理数量。
- NormalizeRun 记录材料版本、提示版本、请求模型、原始输出、校验后结果、用量及每次尝试。
- HumanReview 追加保存复核人、时间、结论、说明及对应的精确材料/提取版本。
- ValidationBatch / ValidationSample 固定跨来源抽样清单、最新材料版本、种子和抽样总体；不按 AI 是否成功筛选样本。
- FieldReview 保存逐字段人工判断及精确 NormalizeRun，校验完整字段清单、缺失值与错误依据；旧表单不能写到重跑结果。累计指标按 Item 最新人工核查去重。
- WorkSession 保存实际工作范围、标准、开始/结束时间、阅读/候选/入选数；禁止同名操作人重叠计时，已结束记录不可覆盖。

`/api/validation` 提供日报、批次、样本和工作计时接口。验收台与 `less report` 共用数据库统计，按可配置本地自然日计算，计划与手动采集分开；未登记的到期任务仍计入计划分母。成功必须在当日截止前完成。来源健康和人工验收指标为导出时的累计信息，不伪装为历史快照。

原文、模型结果、人工判断互不覆盖。原文快照不可变；备份包含数据库、快照和 SHA-256 校验清单，恢复仅写入新库及独立数据目录。

## 3. Codex 执行边界

首期采用 `CodexCliExecutor`，实现 `AIExecutor.execute(material) → AIResult`。通过 `codex exec` 和 JSON Schema 输出结构化结果，Pydantic 再次校验；陈述引用必须与输入段落逐字匹配。模型标签只允许 `reported_claim` 和 `fact_candidate`，不能自动生成 Verified Fact。

每次任务在临时目录中运行，使用只读沙箱，忽略用户配置并关闭 shell、插件、MCP Apps、hooks、浏览器、多 Agent 等工具入口；不传入数据库、Redis 或 API 凭据。输入材料明确作为待分析数据。父进程接收结果并写入业务库。

Codex 使用本机现有 ChatGPT 登录，需要联网并受账号额度约束。CLI 默认模型可能随运行环境变化，因此分别记录请求模型与实际可获取信息；实际模型标识未提供时记未知，费用无法获取时同样记未知。首轮真实调用已获得 token 用量。

官方能力依据：[非交互调用与结构化输出](https://learn.chatgpt.com/docs/non-interactive-mode)、[登录方式](https://learn.chatgpt.com/docs/auth)。本机验证版本为 Codex CLI 0.154.0。

## 4. 调度、恢复与默认值

- 来源默认每 6 小时检查；单轮最多 5 条，新 URL 优先，保留完整 Feed 快照。Feed 解析失败不能记成“无更新”。
- 计划调度每分钟派发一次；历史漏执行槽记为 missed，恢复补采使用当前独立槽。人工采集单独标记，不混入计划成功率。
- 相同材料及任务版本重复入队返回已有任务；显式重新提取创建新记录。
- 采集与 AI 临时失败最多尝试 3 次，重试分别延迟 2、4 分钟；重复消息不会绕过重试时间。
- AI 调用默认超时 180 秒，超时终止子进程组。登录、额度或 CLI 不可用会暂停 AI 队列；人工恢复留下审计记录。
- 中断任务在超时后、且对应数据库锁已释放时进入可重试状态；保留中断原因。
- 自动采集后 AI 提取默认关闭，便于首轮控制账号用量。设置 `LESS_AUTO_NORMALIZE=true` 即自动入队；按钮与 CLI 始终可用。
- 所有 AI 执行共享数据库锁与每日次数预算，默认 `LESS_AI_DAILY_LIMIT=10`、`LESS_TIMEZONE=Asia/Shanghai`。按每次尝试计数，失败和重试也占用额度；预算用尽进入 `budget_wait`，次日重新派发。早期缺失逐次日志的尝试保守估算，报表显式披露。

## 5. 阶段边界与验证

已实现 Week 1 的软件基础，并进入 Week 2：`/api/editorial` 提供有内容修订号的事件骨架、段落关联/取消/恢复、关键陈述、原文证据、独立价值与质量门、编辑决定及历史。证据变动使旧审核失效，按事件行锁与修订号拒绝过时表单。摘录需逐字存在于保存段落；每条关键陈述需已核验支持证据，Context 不抵作 Supporting，Counter 必须说明处理结果。

当前 Inbox 支持手动编辑、陈述更正、规则聚类召回和可恢复合并拆分。`ClusterOperation` 保存聚类前关联、操作后修订号与恢复记录；移动陈述时保持 Evidence ID，旧事件通过 lifecycle / redirected_to 保留去向。恢复必须匹配所有相关事件修订号，不能覆盖后续编辑；恢复后重新核验，不自动复用旧批准。

规则召回处理骨架、文字相似、版本/时间冲突和共享原文。另有独立机器辅助任务提供语义配对建议、价值初筛、事件与 Brief 草稿，共用串行锁、每日预算和额度暂停状态；输入快照与逐字引用校验限制机器输出。配对和排除项审计固定样本，首次盲判后才显示机器结果，追加更正保留历史。完整引用链遍历与独立原始材料配对验收仍未完成。

Brief 提供版本、审核、内部发布、撤回和次日阅读反馈；Today 每日最多 5 条。Signal 提供假设、证据、反证检索日志和显式复评。事件更正使相关 Brief 和 Signal 需重新审核，机器输出不自动批准事实、发布 Brief 或升级 Signal。

测试覆盖幂等、版本保存、原文定位、无效模型输出、重跑保留复核、额度暂停、超时、恢复及计划漏执行；浏览器测试验证原文查看和人工复核操作。测试记录与真实内容分离。

连续运行天数、人工基线、关键字段准确率、漏选与阅读价值尚待真实运行验证。向量检索、云部署和其他 AI 执行器均待具体需求出现后接入。

| 日期 | 变更 |
|---|---|
| 2026-09-20 | 固定已确认选型、本机 Codex 执行方式、数据与审核边界，以及 Week 1 实现范围 |
| 2026-09-20 | 增加验收台、跨来源固定抽样、逐字段人工核查、工作计时、日报导出和每日 AI 次数上限；人工验收仍待执行 |
| 2026-09-21 | 增加手动编辑 Inbox、事件与证据模型、独立两道门与版本失效规则；按完整规划继续推进机器建议、评估、Brief 和 Signal |
| 2026-09-21 | 增加规则聚类召回、合并/拆分/恢复、历史去向、陈述更正及并发修订保护；数据库迁移与 39 项后端测试通过 |
