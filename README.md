# Less

[中文](README.md) | [English](README.en.md)

**Read less. Know more.**

Less 把内容获取当能力，把理解内容当产品。Content Skill / Agent 负责发现、筛选、核验与提炼；本地软件只保存和呈现值得留下的 Brief。

当前版本提供最小闭环：

- `less-content` Skill 交付结构化 Brief 草稿。
- 管理页预览单条草稿或 JSON 数组，明确确认后才逐条保存；中途失败会保留未保存的草稿。
- 配好 SMTP 后，本地调度程序每天早晚自动查找、核验、入库并发送邮件简报。
- Today 按保留日期阅读少量内容，并显示真实来源日期。
- Brief 详情保留事实、价值、判断、限制和具体原始来源。
- Topics 从已保存内容自然生成。

当前规范见 [docs/README.md](docs/README.md)。旧 Content Engine 的代码历史由 `v0.1-content-engine-prototype` tag 保留，旧规范和运行记录仅供追溯。

## 本地运行

仓库固定 Python 3.12（包支持 3.12–3.13），需要 uv、Node.js 与 npm。

```bash
make setup
make dev
```

打开 <http://127.0.0.1:5173>。首次启动会自动创建 `data/less.db`，不需要 Docker、PostgreSQL、Redis 或外部 API Key。

如需覆盖数据库位置或 Today 时区，复制 `.env.example` 为 `.env` 后修改。SQLite URL 使用绝对路径时形如 `sqlite:////absolute/path/to/less.db`。

## 验证

```bash
make test
```

测试包含 SQLite API、Ruff、TypeScript/Vite 构建和 Playwright 浏览器场景。更新后端接口后运行 `make api-types` 同步 OpenAPI 与前端类型。

## Content Skill

仓库级 Skill 位于 `.agents/skills/less-content/`。它可以被 Codex 自动发现，也可以显式使用 `$less-content`。Skill 只输出草稿；手动运行时请在管理页检查并确认保留，已授权的定时任务则由调度程序校验后自动入库。

内容发现采用混合来源策略：先处理任务明确指定的来源，再检查与主题相关的[首选来源清单](.agents/skills/less-content/references/preferred-sources.md)，覆盖不足或需要交叉验证时继续扩展搜索。该清单是版本化的搜索起点，不是白名单，也不会触发自动采集。

观察范围和来源角色沿用原产品蓝图的 Coverage Map 与 Source Map，现由[当前 Content Skill 规范](docs/current/02-content-skill.md)维护；首选清单保留旧来源登记中的具体观察节点，并可按任务补充新节点。

## 早晚自动简报

`make dev` 启动 API、前端和独立的简报调度进程。项目持续运行时，调度进程按 `LESS_TIMEZONE`（默认 `Asia/Shanghai`）每天 06:00 和 18:00 启动内容任务；电脑休眠、项目停止或错过时段时不会补跑。也可单独运行 `.venv/bin/less scheduler`，但不要与 `make dev` 同时运行两个调度进程。数据库中的每日期/时段唯一记录会阻止重复执行。

自动内容任务使用本机已登录的 Codex CLI 及实时网页搜索，按仓库 `less-content` 规范查找、核验并生成结构化 Brief。每轮面向广义知识工作者，使用中英文查询分别寻找应用实践、有依据的观点访谈和重要能力变化；中文区覆盖本土产品、团队及原创经验。按价值选稿，不要求固定条数或语言比例，实际来源与访问缺口记录在 `task_note`。

它重点查看上一 12 小时，并回看最近 24 小时寻找较晚发现的内容；只有日期没有时刻的来源可能在首次核实时收录，邮件只显示来源日期，不推断其具体发布时间。宿主从全库索引召回少量相关旧 Brief，再启动一次去重比较任务；存在歧义的内容不自动保留。高或中等核验把握且通过校验、去重的内容会自动入库；中等把握必须注明限制。没有合格内容也会发送一封简短邮件。邮件是在内容任务完成后发送，可能晚于 06:00 / 18:00。

首次启用前，在仓库根目录创建被 Git 忽略的 `.env`，参考 [`.env.example`](.env.example) 填写以下值：

| 配置 | 用途 |
| --- | --- |
| `LESS_SMTP_HOST`、`LESS_SMTP_PORT` | SMTP 主机及端口；587 使用 STARTTLS，465 使用 TLS |
| `LESS_SMTP_USERNAME`、`LESS_SMTP_PASSWORD` | SMTP 登录名与应用密码 |
| `LESS_MAIL_FROM`、`LESS_MAIL_TO` | 发件与收件邮箱地址 |

不要将密码提交到 Git。调度程序不会把这些配置传入 Codex 子进程。SMTP 未配置时不会运行昂贵的内容任务；该轮会记录失败。Codex 登录可用 `.venv/bin/less preview --slot morning` 或 `--slot evening` 检查：命令使用真实内容生成文本邮件预览，不入库、不发送邮件，也不占用正式调度时段。正式邮件的完整 HTML 与纯文本正文由同一渲染逻辑生成。运行结果保存在 SQLite 的 `digest_runs` 表中；内容任务失败时尽可能发送明确的失败通知，SMTP 发送失败会有限重试并留下失败记录。

HTML 邮件采用暖白与橄榄绿的单栏刊物版式，最大宽度 640px，手机与桌面使用不同留白。正文保留全文和段落，来源、Less 判断及限制分别呈现；正常、空内容、失败与去重待复核邮件共用模板。布局使用表格与内联样式，无需外部字体或图片；不支持媒体查询的邮箱仍能按顺序阅读全文，但留白可能不同。浏览器预览通过不代表全部邮箱客户端兼容。

## 许可与数据

本地数据库、SMTP 密码和邮件内容不应提交。使用内容来源时保留原始链接、日期与限制。

当前默认分支未提供项目级许可证文件；公开可见不等于授予复用许可。第三方依赖及素材保留各自条款。
