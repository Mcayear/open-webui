# 上游合并规则

- 合并或升级上游 Open WebUI 时，优先采用目标上游实现，并逐项检查下方本地修复；每项都须阅读对应详情，在目标上游原始实现上验证，避免本地补丁掩盖问题。不能只凭提交标题、相近功能或无冲突判断已覆盖。
- 上游已覆盖的部分，移除被替代实现、专属接入及失效测试和引用；未覆盖的部分保留并适配，必要的行为回归测试继续保留。
- 合并说明逐项记录目标版本、覆盖范围、验证结果和代码取舍。新增、调整或清理本地修复时，同步更新本文件索引及 [维护详情](docs/local-changes.md)；发布流程等仓库定制不视为待修复缺陷。

# 本地构建约定

- 生产前端保留 `console.error`，移除 `console.log`、`console.debug`；涉及 `vite.config.ts` 或构建流程时核对。具体要求见 [构建约定](docs/local-changes.md#构建约定保留生产错误日志)。

# 待上游覆盖的本地修复

基准为已合并的上游 `v0.12.4`（`33c1978d5`）；第 1–5 项核对于 2026-10-26，第 6–7 项核对于 2026-10-29。后续版本须重新验证，既有合并依据见 [v0.12.4 合并记录](docs/upstream-v0.12.4-merge.md)。各项实现位置、测试命令、场景和清理条件见对应详情。

1. **MinerU 图片保留与检索视觉输入**：云端 ZIP、4.x 内嵌图片、内部文件存储及检索图片传递仍有本地补丁。涉及 MinerU、文件入库、图片权限或检索消息组装时核对。[详情](docs/local-changes.md#mineru-images)
2. **Markdown 加粗闭合兼容**：补充中文标点、尾随空格后的 `**` 闭合，保护代码、链接和转义语义。涉及 Marked 升级或消息 Markdown 渲染时核对。[详情](docs/local-changes.md#markdown-strong)
3. **Responses 推理努力参数转换**：将顶层 `reasoning_effort` 转为 `reasoning.effort`，保留原生配置优先级及 Chat Completions 行为。涉及 OpenAI 路由或高级参数转换时核对。[详情](docs/local-changes.md#responses-reasoning)
4. **分享聊天延迟补滚中断**：初始化已采用上游；仍保留用户上滚后停止两帧补滚的修复。涉及分享页、消息滚动或 `autoScroll` 时核对。[详情](docs/local-changes.md#shared-chat-scroll)
5. **Sub-agent 当前消息图片附件**：合并顶层与当前用户消息附件查找，仅转发请求的文件并准确报告缺失 ID。涉及 `delegate`、附件选择或 sub-agent 消息持久化时核对。[详情](docs/local-changes.md#subagent-images)
6. **模块下载失败恢复**：动态模块下载失败可能显示空白 500；同一标签页 60 秒内最多自动恢复一次并保留错误日志。涉及客户端 hook、路由、SvelteKit 升级或模块加载时核对；底层连接中断原因未确定。[详情](docs/local-changes.md#module-load-recovery)
7. **页面语言与自动翻译提示**：在应用加载前设置 `html.lang`，通过 `translate="no"` 和 `google/notranslate` 声明无需浏览器翻译（也可能影响手动整页翻译）。涉及 HTML 模板、i18n 初始化或翻译策略时核对。[详情](docs/local-changes.md#document-language)

# 本地功能

- **DeepSeek 搜索与网页加载**：Search/Fetch API 接入，共享敏感密钥，独立网页加载选择，以及 Fetch Markdown 转可读文本。涉及搜索提供商、网页加载、URL 安全、配置、管理界面或依赖时阅读 [详情](docs/local-changes.md#deepseek-search-fetch)。合并上游时也须针对新的目标 `dev` 检查部分覆盖情况并验证，按实际范围保留或移除。
