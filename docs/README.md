# Less 文档

当前基线：2026-09-23 · 轻量 Less。

## 当前规范

按以下顺序阅读，后续产品、编辑与开发讨论以这三份文档和用户最新明确决策为依据：

| 文档 | 职责 |
| --- | --- |
| [产品原则](current/00-less-principles.md) | 品牌、价值判断与长期原则 |
| [轻量架构](current/01-less-lite-architecture.md) | 软件边界、Brief / Topic / Source 与最小阅读闭环 |
| [Content Skill](current/02-content-skill.md) | 内容发现、筛选、核验、提炼与 Brief 输出约定 |

内容获取由 Content Skill / Agent 完成；软件负责保存、组织和呈现值得留下的内容。优先跑通 Brief 保留、Today 阅读及原始来源访问，其他能力按真实需求增加。

当前代码已迁移到 SQLite、Brief / Topic / Source 最小内容模型，以及 Today、详情和精简管理界面；实现范围仍以这三份文档为准。原蓝图的 Coverage Map 与 Source Map 已纳入当前 Content Skill 规范，旧采集实现不随之恢复。

## 试扫记录

- [2026-09-24 来源扩充试扫](research/source-expansion-trial-2026-09-24.md)：记录宽泛扫描、AI Coding / Agents 专题扫描的去重结果，以及社媒帖文的可访问性与核验成本。

## 历史资料

旧重型 Content Engine 规范已移至 [archive/content-engine-prototype](archive/content-engine-prototype/ARCHIVED.md)，仅供追溯，不作为当前产品规范。原 Phase 1、Week 1–4 计划与旧验收清单不自动延续。

原目录 `doc/` 已统一为 `docs/`。历史运行记录与来源配置保留在仓库 `operations/`，不属于当前规范。
