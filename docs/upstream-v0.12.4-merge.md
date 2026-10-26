# Open WebUI v0.12.4 合并记录

核对日期：2026-10-26。目标标签：`v0.12.4`，原始提交：`33c1978d5bad52a31df75ea55143025dfad18d16`。合并前本仓库为 `630bb74ce`，包含 GitHub 上已合入的 sub-agent 图片附件修复。本次核对使用目标标签导出的原始文件，未将本地补丁混入上游对照。

## 本地修复逐项核对

| 项目                             | v0.12.4 原始实现的验证结果                                                                                                                             | 合并决策                                                                                                             |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| MinerU 云端 ZIP 图片             | 9 项加载器测试中的云端相对路径及 URL 编码图片场景失败；清理 ZIP 后仍引用相对图片路径。                                                                 | 保留 `_inline_zip_images`。                                                                                          |
| MinerU 4.x 内嵌图片              | Markdown 图片被移除，HTML 图片与纯图片文档返回空正文错误；连同云端共 4 项图片场景未通过。                                                              | 保留 `_MinerUImageParser`、`_preserve_v1_image`；采用上游新增的 V1 Bearer API 密钥认证。                             |
| 图片内部文件存储与检索视觉输入   | 原始 `index_file` 无入库图片转换接入，检索上下文仍不能将命中图片附加为视觉输入。既有文件权限检查正常。                                                 | 保留入库转换、`min_replacement_url_length=0`、检索图片提取及消息接入；沿用上游权限检查。                             |
| Markdown 加粗闭合                | 使用原始消息组件全部扩展、`breaks: true` 和锁定的 Marked 9.1.6 执行 35 个场景，18 项通过、17 项失败。中文标点和尾随空格闭合仍不兼容。                  | 保留 `strong-extension.ts`、专属注册及回归测试。                                                                     |
| Responses 推理努力转换           | 从模型高级配置经实际 `generate_chat_completion` 路由到提供商请求，6 个 Responses 场景仍含顶层 `reasoning_effort`；6 个 Chat Completions 对照场景正常。 | 保留 `convert_to_responses_payload` 中的本地映射，维持原生 `reasoning.effort` 优先级及 summary。                     |
| 分享聊天重复初始化               | 编译原始分享路由与消息组件，以隔离分享接口运行浏览器测试，初始化只请求 1 次；向上滚动、加载更早消息、切换分享页及消息链接定位均可用。                  | 移除本地 `initializeSharedChat`，采用上游 `loadAndScroll` 及响应式调用。                                             |
| 分享聊天延迟补滚中断             | 执行实际 `scrollToBottom` 函数并控制动画帧：首帧后用户向上滚动到 100，原始实现在后续帧仍置底至 1000；原始分享容器也未同步更新 `autoScroll`。           | 保留分享容器滚动事件与消息组件的补滚条件检查；为 `autoScroll` 声明 boolean 类型。合并版同场景保持 100。              |
| Sub-agent 当前消息图片附件       | 对原始 `delegate` 执行仅在 `metadata.user_message.files` 中附图的场景，返回 `file_ids not attached or unavailable: image-1`，未创建 sub-agent。        | 保留本地附件合并、匹配与去重，以及 6 项回归测试。                                                                    |
| DeepSeek Search / Fetch 本地功能 | 检查 `v0.12.4` 与当日上游 `dev`（`7b303cf49`）的原始 API 路径、配置回退、提供商、加载器注册和管理界面，均无对应支持。                                  | 保留 Search/Fetch、Markdown 解析和配置接入；适配上游搜索配置显隐行为，确保关闭搜索时仍可配置 DeepSeek 网页加载密钥。 |

## 冲突处理与仓库定制

- `WebSearch.svelte` 采用上游只在启用搜索时显示引擎设置的结构，保留 DeepSeek 选项；去掉冲突产生的重复引擎选择区。网页加载选择 DeepSeek 且搜索关闭或搜索引擎不为 DeepSeek 时，单独显示共享敏感密钥输入。
- 分享页初始化采用上游实现，只保留尚未被覆盖的滚动处理。
- `uv.lock` 采用上游 MCP 2.3.0，并保留 DeepSeek Markdown 解析直接依赖 `markdown-it-py==4.2.0`；完整/slim 依赖清单一致，离线锁文件检查通过。
- 继续删除本仓库已移除的 PyPI 发布工作流；GitHub Release、Docker 多架构发布、slim 独立构建与缓存等仓库定制继续保留，不列为待上游修复缺陷。

## 合并后验证

- Python 3.11 和 3.12：`python -m unittest discover -s tests -v`，各 46 项通过（MinerU 9、Responses 8、DeepSeek 23、sub-agent 6）。测试依赖按项目版本隔离安装。
- 模型高级配置到实际路由和提供商 HTTP 边界：12 个 Responses / Chat Completions 场景全部通过，覆盖流式/非流式、原生 summary、原生 effort 优先级。使用隔离提供商响应，未调用真实模型服务。
- 执行合并后的实际 `index_file` 图片转换块和 `process_chat_payload` 检索接入块：小图片保存为 `/api/v1/files/.../content`；图片内容保留、重复引用和已有附件去重；关闭视觉能力不读取图片；所有者、管理员、显式授权可读，未授权与匿名不可读，均通过。数据库和存储 IO 使用隔离边界。
- 编译实际分享页与消息组件运行隔离浏览器测试：只请求一次，向上滚动位置稳定、加载早期消息、页面切换及消息定位通过，无运行时异常；受控动画帧验证延迟补滚可中断。消息正文子组件和分享 API 使用测试替身。
- `npm run test:frontend -- --run`：39 项通过，其中 Markdown 加粗 35 项。
- `npm ci --force`、`npm run build`、`npm run i18n:parse` 通过；国际化检查没有产生文件差异。
- Ruff 格式与逻辑检查、相关 Prettier 检查、Python 编译、`uv lock --check --offline --python 3.12`、`git diff --check` 通过。Ruff 本地运行排除 `.git` 中旧版本核对材料，避免将其视为产品代码；GitHub CI 的新检出不包含这些本地材料。
- 完整 `npm run check` 未通过。原始 v0.12.4 在相同锁定依赖下为 5,675 个错误、188 个警告；合并版为 5,672 个错误、188 个警告。按文件与错误信息规范化比较无新增诊断，`autoScroll` 类型声明消除 3 个上游诊断。未把生产构建成功表述为类型检查通过。

未重复调用真实 MinerU、DeepSeek 或模型服务；上述 HTTP、数据库和存储隔离验证不能替代这些服务的真实集成验证。未在文档或测试中写入真实 API 密钥。
