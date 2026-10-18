# 上游合并规则

- 合并或升级上游 Open WebUI 时，优先采用目标上游版本的实现。
- 每次合并上游时，都要逐项检查下方“待上游覆盖的本地修复”，确认目标上游版本是否已修复，并通过相关场景或回归测试验证；不能只凭提交标题、相近功能或无合并冲突判断。
- 若上游已覆盖对应修复，移除本仓库中被替代的实现及其专属接入代码，以目标上游代码为准；同步清理只适用于旧实现的测试和引用，必要的行为回归测试可以保留。
- 若上游仍未覆盖问题，保留并适配必要的本地补丁。若只覆盖部分场景，只移除已经被替代的部分，并在合并说明中记录判断依据和验证结果。
- 核对上游是否覆盖时，应在目标上游原始实现上验证，避免本地补丁使测试通过而误判。合并说明应逐项记录目标版本、覆盖范围、验证结果及保留或移除的代码。
- 新增或调整本地修复时，同步更新本清单中的问题、实现位置、验证场景和上游核对依据。上游覆盖后更新状态或删除失效条目；不要把发布流程等仓库定制视为待修复缺陷。

# 待上游覆盖的本地修复

核对日期：2026-10-17。以下以本仓库当前已合并的上游 `v0.12.3`（`91ea4e342`）为基准，不能据此认定之后的上游版本仍有问题。下次合并必须针对新的目标版本重新验证。

## 1. MinerU 图片保留、内部文件存储与检索视觉输入

- **问题与上游状态**：`v0.12.3` 的云端解析仍只读取结果 ZIP 中的 Markdown，图片相对路径在 ZIP 清理后失效；MinerU 4.x 自托管 V1 API 会主动删除 Markdown data URI 图片和 HTML `<img>`。支持 4.x API 本身不代表图片问题已解决。本次在原始 `v0.12.3` 上重新运行验证，4 个图片保留场景仍未通过，入库图片转换和检索视觉传递也未覆盖；保留对应本地补丁及接入。上游已有的文件权限检查继续沿用。
- **本地行为**：云端 ZIP 图片在清理前转成 data URI；4.x Markdown 内嵌图片保留，HTML 内嵌图片转换成 Markdown；入库时把图片保存为内部文件并替换引用，小图片同样保存；检索命中图片时按用户权限读取，去重后附加到支持视觉的模型输入。
- **实现位置**：`backend/open_webui/retrieval/loaders/mineru.py` 的 `_inline_zip_images`、`_MinerUImageParser`、`_preserve_v1_image`；`backend/open_webui/routers/retrieval.py` 的图片入库接入；`backend/open_webui/utils/files.py` 的 `min_replacement_url_length` 参数；`backend/open_webui/utils/middleware.py` 的 `extract_source_images`、`add_images_to_last_user_message` 及 `apply_source_context_to_messages`、`process_chat_payload` 中的图片接入。
- **验证**：`python -m unittest discover -s tests -p test_mineru_images.py -v`，依赖 `requests`、`fastapi`、`langchain-core`。覆盖云端 ZIP 相对路径及 URL 编码、4.x Markdown/HTML 内嵌图片、纯图片文档，以及 3.x 兼容、超时和 Markdown 大小限制。另须验证入库后图片成为 `/api/v1/files/.../content` 引用（含小图片），有权限的视觉模型收到去重图片，关闭视觉能力时不附加图片，文件权限检查仍生效；现有加载器测试不能替代这些链路验证。2026-10-17 合并后，9 项加载器测试在 Python 3.11/3.12 均通过；在隔离存储边界下执行实际入库图片处理代码和检索消息接入代码，验证小图片存储、重复引用和已有附件去重、关闭视觉能力时不读取图片，以及所有者、管理员、显式授权、未授权和匿名访问权限。
- **清理条件**：上游分别覆盖云端图片、4.x 内嵌图片、内部文件存储、检索视觉传递后，按实际覆盖范围移除对应补丁及专属接入。保留目标上游的 MinerU API 实现、错误处理和大小限制。移除自定义文件转换参数前检查所有调用点，清理专属测试及 `.github/workflows/backend.yaml` 中不再适用的测试接入，并保留其余回归验证。

## 2. Markdown 加粗闭合兼容

- **问题与上游状态**：`v0.12.3` 的消息 Markdown 渲染仍没有覆盖中文标点或尾随空格后的 `**` 闭合场景，例如 `**中文。**测试`、`**English. **Test`，会显示原始星号而不能按预期加粗。本次使用原始组件的全部 Marked 扩展注册和锁定的 Marked 9.1.6 验证，35 个场景中 17 个未通过；保留本地扩展及注册。
- **本地行为**：通过 `relaxedStrong` 扩展补充上述加粗场景，并优先保留 Marked 的标准解析；代码、链接、HTML 属性和转义中的星号不应错误地闭合加粗。
- **实现位置**：`src/lib/utils/marked/strong-extension.ts`；`src/lib/components/chat/Messages/Markdown.svelte` 中的导入和 `marked.use(relaxedStrong)` 注册。
- **验证**：`npm run test:frontend -- --run src/lib/utils/marked/strong-extension.test.ts`。核对中英文标点、尾随空格、紧邻后续文字、多段加粗、内部斜体/代码，以及代码块、链接、HTML、转义、三重星号、未闭合片段和流式补齐后的渲染。验证上游时应移除本地扩展注册，使用目标上游实际的 Markdown 渲染路径和依赖版本。
- **清理条件**：上游原始消息渲染覆盖上述行为后，移除 `strong-extension.ts`、组件中的专属导入和注册；清理依赖旧扩展的测试，必要的行为回归测试改为验证上游渲染实现。

## 3. Responses API 推理努力参数转换

- **问题与上游状态**：`v0.12.3` 的 `convert_to_responses_payload` 仍没有转换 `reasoning_effort`。连接选择 Responses 接口、模型高级配置设置推理努力（例如 `gpt-6.1-sol` 的自定义 `xhigh`）后，仍发送 Chat Completions 的顶层字段，兼容服务报 `Unsupported parameter: reasoning_effort`。2026-10-16 实测 `v0.12.2` 原始请求返回 HTTP 400。2026-10-17 对原始 `v0.12.3` 的实际路由进行提供商边界隔离验证，流式/非流式与原生推理选项组合的 6 个 Responses 场景均仍发送顶层字段；保留本地映射。
- **本地行为**：仅在 Chat Completions 转 Responses 时移除顶层 `reasoning_effort`，把非空值映射到 `reasoning.effort`；保留 `reasoning.summary` 等原生选项，已显式配置的原生 `reasoning.effort` 优先；未设置时不添加推理配置。Chat Completions 接口继续使用顶层字段，不限制模型名或努力值。
- **实现位置**：`backend/open_webui/routers/openai.py` 的 `convert_to_responses_payload` 中推理努力转换代码。
- **验证**：`python -m unittest discover -s tests -p test_openai_responses.py -v`，仅需 Python 标准库。8 项测试覆盖流式/非流式请求、自定义努力值、原生选项保留与优先级、空值和 Chat Completions 兼容。2026-10-16 实测修复后两种请求均返回 HTTP 200 并完成，返回的 `reasoning.effort` 均为 `xhigh`。2026-10-17 合并后，8 项测试在 Python 3.11/3.12 均通过；从模型高级配置经实际路由到最终提供商请求的 12 个隔离场景均通过，覆盖 Responses/Chat Completions、流式/非流式、原生 summary 保留和原生 effort 优先。本次未重复调用真实模型服务。升级时仍须验证从模型高级配置到最终 Responses 请求的实际路径；不要将 API 密钥写入文档或测试。
- **清理条件**：目标上游已把高级配置中的推理努力正确传递为 Responses 原生参数，且上述场景通过后，移除本地映射代码，保留上游转换实现；同步调整只依赖旧函数或旧路径的测试，避免重复转换或覆盖原生配置。

## 本地功能：DeepSeek 搜索提供商

- **功能与参考**：工具“联网搜索”支持将 DeepSeek 作为搜索引擎，调用 DeepSeek Search API（`POST https://api.deepseek.com/v1/tools/search`），参考 [DeepSeek 搜索文档](https://api-docs.deepseek.com/zh-cn/guides/search)。请求携带 Bearer API 密钥、用户查询、`count`（限制为 1 至 50）和 `need_content: true`；结果优先使用 `summary`，其次使用 `snippet` 或 `content`，并沿用现有域名过滤逻辑。
- **配置**：优先读取 `DEEPSEEK_SEARCH_API_KEY`，未设置时兼容读取 `DEEPSEEK_API_KEY`。管理界面在联网搜索引擎列表中提供 DeepSeek，并使用敏感 API 密钥输入框。
- **实现位置**：`backend/open_webui/retrieval/web/deepseek.py` 的 API 客户端与结果转换；`backend/open_webui/config.py` 的配置项；`backend/open_webui/routers/retrieval.py` 的提供商注册；`src/lib/components/admin/Settings/WebSearch.svelte` 及 `src/lib/i18n/locales/{en-US,zh-CN}/translation.json` 的管理界面和翻译；`tests/test_deepseek_search.py` 的回归测试；`README.md` 的配置说明。
- **验证**：运行 `python -m unittest discover -s tests -p test_deepseek_search.py -v`、`uvx --from ruff ruff check backend/open_webui/retrieval/web/deepseek.py tests/test_deepseek_search.py`、相关 Python 编译检查、`npx prettier --check`（修改的前端和翻译文件）以及 `git diff --check`。测试覆盖请求认证、参数范围、结果字段回退和域名过滤；测试不得写入真实 API 密钥。
- **上游核对**：已在上游 `dev` 提交 `079fb19e7`（2026-10-18 核对）原始实现中搜索 DeepSeek 提供商、配置和管理界面，未发现对应支持，因此保留本地实现。后续合并或升级上游时，必须针对新的目标 `dev` 提交重新检查 API 路径、配置回退、提供商注册、界面选项和行为测试；若上游覆盖其中部分内容，只移除已被覆盖的本地接入，并保留必要的回归测试。
