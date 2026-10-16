# Less

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

需要 Python 3.12、uv 和 Node.js。

```bash
make setup
make start
```

使用 `make start` 统一启动前端、API 和简报调度器，`make stop` 统一关闭，`make status` 检查状态。这三个命令当前面向 macOS。启动完成后命令即返回，服务由系统托管；关闭浏览器、终端或 Codex 不会停止 Less。`make dev` 是前台控制模式，Ctrl+C 或终端正常关闭时会统一停止三个服务。

默认打开 <http://127.0.0.1:5173>；端口被占用时自动选取 5174–5183 并记住选择，以启动输出或 `make status` 的地址为准。也可用 `.venv/bin/python -m less.services start --port 5174` 指定端口。API 固定使用 8000，遇到其他进程占用时会明确报错，不终止其他项目。首次启动会自动创建 `data/less.db`，不需要 Docker、PostgreSQL、Redis 或外部 API Key。

如需覆盖数据库位置或 Today 时区，复制 `.env.example` 为 `.env` 后修改。SQLite URL 使用绝对路径时形如 `sqlite:////absolute/path/to/less.db`。

### Codex 与 Antigravity

在 Codex 或 Antigravity 的 Agent／内置终端中执行 `make start`（或 `make dev`），Less 会根据启动进程的祖先链识别平台，并固定本次内容任务使用的工具：Codex 调用 `codex`，Antigravity 调用 `agy`。启动时会显示所选工具。两种平台共用数据库、网页和内容规范；内容生成及历史去重使用同一平台，切换平台后需要重新启动 Less。

`LESS_AGENT_PROVIDER` 默认为 `auto`。从普通终端启动、祖先进程不可读取或环境无法识别时，需要明确指定：

```bash
LESS_AGENT_PROVIDER=codex make start
LESS_AGENT_PROVIDER=antigravity make start
```

显式配置优先于自动识别；也可写入 `.env`，但希望随启动平台切换时应保持 `auto`。识别失败或对应 CLI 不在 `PATH` 时，启动会立即报错；登录、权限或调用失败不会自动改用另一个平台。只启动 API／前端不涉及内容任务时无需选择 Agent。

Codex 需要安装并登录 Codex CLI。Antigravity 需要安装支持 `-p`、`--output-format json`、`--json-schema`、`--print-timeout` 和 `--sandbox` 的 Antigravity CLI；本机验证参数的版本为 `agy 1.2.13`。先在交互终端运行 `agy` 完成登录，再运行下方预览验收。IDE 登录和 CLI 的缓存登录是否可用，以预览结果为准。

Antigravity 的非交互任务遵循 CLI 权限设置；退出码为 0 也可能发生工具被拒绝的情况，Less 会拒收识别到的权限拒绝输出。请根据 CLI 的诊断配置搜索工具和原文读取权限。宽泛发现需要动态扩展来源，原文读取可在 `~/.gemini/antigravity-cli/settings.json` 的现有 `permissions.allow` 中加入 `read_url(*)`；这是全局网页读取授权，如希望限制来源可改用具体域名，但未授权来源可能无法核验。保留现有其他配置，不开启全部工具自动批准。参见 [Antigravity 非交互调用](https://antigravity.google/docs/cli/headless/)和[权限文档](https://www.antigravity.google/docs/permissions?tab=cli)。

两种工具都在仅包含内容规范和任务输入的临时目录中执行，不传递 `LESS_` 配置或 SMTP 凭据。Codex 使用只读 sandbox；Antigravity 使用其 `--sandbox` 并在提示词中禁止写文件，两者的权限机制不同，Antigravity 的 sandbox 不等同于 Codex 的只读模式。

分别检查真实搜索、内容核验、历史去重与邮件预览：

```bash
LESS_AGENT_PROVIDER=codex .venv/bin/less preview --slot morning
LESS_AGENT_PROVIDER=antigravity .venv/bin/less preview --slot morning
```

预览不入库、不发送邮件、不占用正式调度时段，但会使用对应账号的推理额度。

## 验证

```bash
make test
```

测试包含 SQLite API、Ruff、TypeScript/Vite 构建和 Playwright 浏览器场景。更新后端接口后运行 `make api-types` 同步 OpenAPI 与前端类型。

## Content Skill

仓库级 Skill 位于 `.agents/skills/less-content/`，Codex 和 Antigravity 共用这一份。Codex 可显式使用 `$less-content`；Antigravity 可按名称调用或直接要求阅读 `SKILL.md`。自动任务直接指定规范文件路径。Skill 只输出草稿；手动运行时请在管理页检查并确认保留，已授权的定时任务则由调度程序校验后自动入库。

内容发现采用混合来源策略：先处理任务明确指定的来源，再检查与主题相关的[首选来源清单](.agents/skills/less-content/references/preferred-sources.md)，覆盖不足或需要交叉验证时继续扩展搜索。该清单是版本化的搜索起点，不是白名单，也不会触发自动采集。

观察范围和来源角色沿用原产品蓝图的 Coverage Map 与 Source Map，现由[当前 Content Skill 规范](docs/current/02-content-skill.md)维护；首选清单保留旧来源登记中的具体观察节点，并可按任务补充新节点。

## 早晚自动简报

前端、API 和调度器统一由 `make start` / `make stop` 管理，三个进程分别由 macOS 托管，异常退出时各自重启。显式执行 `make stop` 后，三个服务保持停止，重新登录也不会自行启动；再次 `make start` 才重新启用。Less 处于启动状态时，会在用户登录后恢复运行，电脑仍须保持唤醒、外置项目盘仍须可访问。

调度器按 `LESS_TIMEZONE`（默认 `Asia/Shanghai`）每天 06:00 和 18:00 启动内容任务；休眠或服务停止导致错过时段时不会补跑。单实例锁和每日期/时段唯一记录阻止重复执行。停止 Less 时会取消当前内容任务并尽可能记录为 `interrupted`。切换内容平台先 `make stop`，再用新的 `LESS_AGENT_PROVIDER` 执行 `make start`。服务只保存所选平台和必要的进程环境，SMTP 配置仍从仓库 `.env` 读取。

旧 `make scheduler-install` / `scheduler-status` / `scheduler-uninstall` 命令分别兼容映射到统一的 start / status / stop。`.venv/bin/less scheduler` 仅供独立调试，不与统一服务并行运行。

运行日志保存在 `data/less-scheduler.log`，按 2 MB 轮换并保留三份历史；服务启动诊断在 `~/Library/Logs/Less/scheduler-service.log`，API 和前端日志也在该目录，避免 launchd 在执行前访问外置盘上的工作目录或日志。获得单实例锁后，调度器将旧的 `running` / `saved` 记录标为 `interrupted`，保留已保存内容，不补跑或重发邮件，以免重复发送。停止服务时会取消当前内容子进程，并尽可能记录中断；强制结束或断电留下的状态由下次启动恢复。

自动内容任务使用启动时选定且已登录的 Codex CLI 或 Antigravity CLI 及实时网页搜索，按仓库 `less-content` 规范查找、核验并生成结构化 Brief。每轮面向广义知识工作者，使用中英文查询分别寻找应用实践、有依据的观点访谈和重要能力变化；中文区覆盖本土产品、团队及原创经验。按价值选稿，不要求固定条数或语言比例，实际来源与访问缺口记录在 `task_note`。

它重点查看上一 12 小时，并回看最近 24 小时寻找较晚发现的内容；只有日期没有时刻的来源可能在首次核实时收录，邮件只显示来源日期，不推断其具体发布时间。宿主从全库索引召回少量相关旧 Brief，再启动一次去重比较任务；存在歧义的内容不自动保留。高或中等核验把握且通过校验、去重的内容会自动入库；中等把握必须注明限制。没有合格内容也会发送一封简短邮件。邮件是在内容任务完成后发送，可能晚于 06:00 / 18:00。

首次启用前，在仓库根目录创建被 Git 忽略的 `.env`，参考 [`.env.example`](.env.example) 填写以下值：

| 配置 | 用途 |
| --- | --- |
| `LESS_SMTP_HOST`、`LESS_SMTP_PORT` | SMTP 主机及端口；587 使用 STARTTLS，465 使用 TLS |
| `LESS_SMTP_USERNAME`、`LESS_SMTP_PASSWORD` | SMTP 登录名与应用密码 |
| `LESS_MAIL_FROM`、`LESS_MAIL_TO` | 发件与收件邮箱地址 |

不要将密码提交到 Git。调度程序不会把这些配置传入内容 Agent 子进程。SMTP 未配置时不会运行昂贵的内容任务；该轮会记录失败。对应 CLI 的登录及任务能力可用 `.venv/bin/less preview --slot morning` 或 `--slot evening` 检查：命令使用真实内容生成文本邮件预览，不入库、不发送邮件，也不占用正式调度时段。正式邮件的完整 HTML 与纯文本正文由同一渲染逻辑生成。运行结果保存在 SQLite 的 `digest_runs` 表中；内容任务失败时尽可能发送明确的失败通知，SMTP 发送失败会有限重试并留下失败记录。

HTML 邮件采用暖白与橄榄绿的单栏刊物版式，最大宽度 640px，手机与桌面使用不同留白。正文保留全文和段落，来源、Less 判断及限制分别呈现；正常、空内容、失败与去重待复核邮件共用模板。布局使用表格与内联样式，无需外部字体或图片；不支持媒体查询的邮箱仍能按顺序阅读全文，但留白可能不同。浏览器预览通过不代表全部邮箱客户端兼容。
