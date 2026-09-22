# Less

**Read less. Know more.**

Less 把内容获取当能力，把理解内容当产品。Content Skill / Agent 负责发现、筛选、核验与提炼；本地软件只保存和呈现值得留下的 Brief。

当前版本提供最小闭环：

- `less-content` Skill 交付结构化 Brief 草稿。
- 管理页预览草稿，明确确认后才保存。
- Today 按保留日期阅读少量内容，并显示真实来源日期。
- Brief 详情保留事实、价值、判断、限制和具体原始来源。
- Topics 从已保存内容自然生成。

当前规范见 [docs/README.md](docs/README.md)。旧 Content Engine 的代码历史由 `v0.1-content-engine-prototype` tag 保留，旧规范和运行记录仅供追溯。

## 本地运行

需要 Python 3.12、uv 和 Node.js。

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

仓库级 Skill 位于 `.agents/skills/less-content/`。它可以被 Codex 自动发现，也可以显式使用 `$less-content`。Skill 只输出草稿，不会自动写入内容库；请在管理页检查并确认保留。
