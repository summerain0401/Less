# 首次技术验证记录 · 2026-09-20

本记录为软件初次联调，不代表 Week 1 或 Phase 1 验收通过。

## 实际验证

- PostgreSQL / Redis 已通过本机 Compose 启动；数据库迁移完成。
- 登记 13 个 Source，逐一进行真实接入检查；每次初检仅取一个条目，降低初始采集量。
- 11 个节点成功获取并保存正文：Google Research、Google DeepMind、Hugging Face、GitHub Engineering、PyTorch、LangGraph Releases、Ollama Releases、Simon Willison、Lilian Weng、Latent Space、OpenAI Codex Releases。
- OpenAI News Feed 可读取，但初检文章返回 403；HN RSS 返回 502。两者标为 Needs Review，未计入实际接通数，也未以搜索摘要替代正文。
- PyTorch 初始 Feed 地址返回 404，改为实测可用的 `https://pytorch.org/feed/`。
- LangGraph 的短发布日志暴露正文长度限制问题，已增加显式 Feed content 的短文本解析并成功复测。
- Codex CLI 0.154.0 使用已有 ChatGPT 登录成功完成一条真实 Ollama 发布记录的 Normalize；耗时约 27 秒，输出包含原文段落引用、作者主张与版本标识冲突提示。未将此结果标为人工批准。
- 首轮备份在独立 `less_restore_validation_20260920` 数据库及独立快照目录恢复：11 个 Items、23 个快照引用通过核对，业务库未被覆盖。
- 第二条真实材料通过 Redis → Celery Worker → Codex CLI 完成提取，验证后台路径可用。
- 最后一轮后端 14 项测试、浏览器 3 项测试通过；类型检查、前端生产构建和 Alembic 模型/迁移一致性检查通过。页面已在桌面及移动视口检查，截图保存在本地 `data/qa/`。

沙箱内第一次 CLI 调用失败，允许访问本机登录与网络后成功。失败次数保留在对应任务中；当时尚未增加逐次尝试日志，因此该早期记录无完整逐次日志。后续版本已持久化每次尝试及错误。

## 仍需运行验证

- [ ] 连续 3 天计划采集及成功率统计。
- [ ] 至少 30 个跨来源材料的关键字段人工核查。
- [ ] 两次独立手工筛选的来源范围、耗时和质量基线。
- [ ] 确认每日观察截止时间、审核节奏及账号用量预算。
- [ ] 复核来源覆盖，尤其补足不可用 Discovery 来源和独立反面实践。

Feed 中的历史材料只用于接入验证，不能计为当天新内容。当前结果没有证明筛选节时、内容稳定供给或 Signal 价值。
