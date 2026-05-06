# project-helper 技术点讲解与总结

本文面向第一次接触本项目的开发者，目标是帮助你快速建立“这套系统如何工作、代码从哪里读、改动时要注意什么”的整体地图。

project-helper 是一个项目学习助手：用户输入 GitHub 仓库地址后，后端会规范化地址、克隆或更新仓库、扫描源码、生成中文分析报告，并把结果缓存到 SQLite。前端通过实时进度流展示分析过程，报告生成后还可以基于源码工具做交互式问答。

## 1. 项目结构

```text
.
├── README.md
├── TESTING_CHECKLIST.md
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI 入口与 API 路由
│   │   ├── analyzer.py      # 分析流程、SSE 格式、问答流
│   │   ├── repository.py    # GitHub URL 规范化、项目 ID、Git 克隆/更新
│   │   ├── source_scan.py   # 源码扫描、技术栈识别、代码搜索
│   │   ├── llm.py           # DeepSeek-compatible LLM、LangChain Agent 工具
│   │   ├── database.py      # SQLite 项目缓存
│   │   └── config.py        # 环境变量与路径配置
│   ├── tests/
│   │   ├── e2e/             # API 主链路测试
│   │   └── unit/            # 模块级测试
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── pytest.ini
└── frontend/
    ├── src/
    │   ├── App.vue          # 单页应用主体、状态流与交互逻辑
    │   ├── main.js
    │   └── styles.css
    ├── package.json
    └── vite.config.js
```

整体可以理解成两层：

- 后端负责“可信执行”：接收仓库 URL、管理缓存、克隆代码、扫描源码、调用 LLM 或本地 fallback、输出 SSE。
- 前端负责“学习体验”：创建任务、展示实时步骤、渲染 Markdown 报告、发起流式问答、管理历史项目。

## 2. 技术栈

后端：

- FastAPI：提供 REST API 和 `StreamingResponse`。
- SQLite：保存项目记录、分析报告和扫描摘要。
- GitPython：执行浅克隆和更新本地仓库副本。
- LangChain + `langchain-openai`：通过 OpenAI-compatible API 调用 DeepSeek，并构建源码问答 Agent。
- anyio：把阻塞的 Git、扫描、LLM 调用放到线程中执行，避免堵塞 async 流。
- pytest + FastAPI TestClient：覆盖模块行为和核心 API 链路。

前端：

- Vue 3 + Vite：单页应用开发与构建。
- marked + DOMPurify：把后端 Markdown 报告渲染为安全 HTML。
- Naive UI：用于删除确认弹窗等交互组件。
- lucide-vue-next：图标体系。

## 3. 核心业务链路

用户从前端输入仓库地址后，主链路如下：

```text
用户输入 GitHub URL
  -> POST /api/projects
  -> normalize_repo_url()
  -> SQLite upsert projects
  -> 前端建立 EventSource
  -> GET /api/projects/{id}/analyze/stream
  -> clone_or_update()
  -> scan_repository()
  -> generate_llm_report()
       -> 如果无 DEEPSEEK_API_KEY，使用 local_report()
  -> db.save_analysis()
  -> SSE done
  -> 前端重新拉取项目详情并展示报告
```

对应核心文件：

- `backend/app/main.py`：定义 API，包括创建项目、查询项目、置顶、删除、分析流、问答流。
- `backend/app/analyzer.py`：定义 `analyze_project_stream()`，串起 clone、scan、summarize、save 四个阶段。
- `backend/app/database.py`：负责项目记录和报告缓存。
- `frontend/src/App.vue`：负责创建任务、监听 SSE、更新进度条、展示报告和问答。

一个重要设计点是：`POST /api/projects` 只创建或返回项目记录，不直接执行分析。真正耗时的分析发生在 `GET /api/projects/{project_id}/analyze/stream` 中，这样前端可以用 SSE 持续接收进度。

## 4. API 与状态流转

主要 API：

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查，返回模型名和 LLM 是否配置 |
| `GET` | `/api/projects` | 获取项目列表，默认不带完整报告 |
| `POST` | `/api/projects` | 创建项目或返回已存在项目 |
| `GET` | `/api/projects/{project_id}` | 获取项目详情和完整报告 |
| `PATCH` | `/api/projects/{project_id}/pin` | 置顶或取消置顶 |
| `DELETE` | `/api/projects/{project_id}` | 删除 SQLite 记录和本地仓库副本 |
| `GET` | `/api/projects/{project_id}/source/tree` | 获取已分析项目的可预览源码目录树 |
| `GET` | `/api/projects/{project_id}/source/file?path=...` | 安全读取仓库内单个文本源码文件 |
| `GET` | `/api/projects/{project_id}/analyze/stream` | SSE 分析进度流 |
| `POST` | `/api/projects/{project_id}/chat/stream` | 流式源码问答 |

项目状态主要有：

- `created`：项目已入库，但还未分析。
- `cloning`：正在克隆或更新仓库。
- `scanning`：正在扫描目录、技术栈、入口和符号。
- `summarizing`：正在生成报告。
- `ready`：报告已生成并缓存。
- `failed`：分析异常。

`Database.update_status()` 会在分析流程不同阶段更新状态；`Database.save_analysis()` 会把状态置为 `ready` 并保存报告。

## 5. SSE 实时进度

分析进度使用 Server-Sent Events。后端的关键函数是 `analyzer.sse(event, data)`，它输出标准帧：

```text
event: progress
data: {"step": "scan", "message": "正在扫描目录、技术栈和核心文件..."}

```

分析流中的事件类型：

- `progress`：阶段性进度，常见 `step` 有 `clone`、`scan`、`summarize`。
- `cached`：命中已完成报告缓存，不重复克隆和扫描。
- `done`：分析完成。
- `failed`：分析失败，携带错误信息。

前端在 `streamAnalysis(projectId)` 中使用 `EventSource` 监听这些事件。收到 `progress` 时追加日志；收到 `done` 时关闭连接、重新请求项目详情并刷新项目列表；收到 `failed` 或连接错误时更新错误提示并停止 loading。

问答接口也使用 SSE 格式返回，但前端没有使用 `EventSource`，而是用 `fetch()` 读取 `ReadableStream`。原因是问答是 `POST` 请求，需要提交 JSON body；浏览器原生 `EventSource` 只支持 GET。前端通过 `reader.read()` 累积 buffer，再按 `\n\n` 切分 SSE 帧，并交给 `parseSse()` 和 `handleChatEvent()` 处理。

问答流事件：

- `token`：一段回答文本。
- `done`：回答完成。
- `failed` 或 `error`：回答失败。

## 6. SQLite 缓存设计

SQLite 数据库路径来自 `Settings.db_path`，默认位于：

```text
.project-helper-data/project_helper.sqlite3
```

本地仓库副本默认位于：

```text
.project-helper-data/repos/{project_id}
```

`projects` 表字段包括：

- `id`：项目 ID，由规范化后的 repo URL 计算 SHA1 前 16 位得到。
- `repo_url`：规范化后的仓库地址，有唯一索引。
- `name`：仓库名。
- `local_path`：本地克隆目录。
- `status`：当前状态。
- `report`：Markdown 报告。
- `summary_json`：扫描摘要 JSON。
- `created_at` / `updated_at`：时间戳。
- `pinned_at`：置顶时间，兼容旧表结构时通过 `ALTER TABLE` 增补。

缓存命中逻辑在 `analyze_project_stream()` 中：

```text
如果当前项目 status == "ready" 且 report 非空
  -> 发送 cached
  -> 发送 done
  -> 直接返回
```

这能避免重复克隆、扫描和 LLM 调用。项目列表接口调用 `db.list_projects(include_report=False)`，会把大字段 `report` 清空，只保留列表页需要的摘要信息，减少接口负载。

删除项目时，后端先删 SQLite 记录，再尝试删除本地仓库副本。删除目录前会确认 `local_path` 位于 `settings.clone_dir` 下，避免误删 clone 根目录或仓库外路径。

## 7. Git 克隆与源码扫描

`backend/app/repository.py` 负责仓库地址和克隆：

- `normalize_repo_url()` 只接受 HTTP/HTTPS URL。
- 默认只允许 `github.com` 和 `www.github.com`，配置来自 `PROJECT_HELPER_ALLOWED_HOSTS`。
- 会去掉 `.git` 后缀，并把多余路径截断为 `owner/repo`。
- `project_id_for()` 用规范 URL 生成稳定 ID。
- `clone_or_update()` 使用浅克隆 `depth=1`，已有 `.git` 时执行 `fetch(depth=1)` 和 `reset --hard origin/HEAD`。

扫描逻辑在 `backend/app/source_scan.py`：

- `iter_source_files()` 通过 `os.walk()` 遍历文本源码和配置文件，跳过 `.git`、`node_modules`、`dist`、`.venv`、缓存目录等。
- 单文件大小限制为 350KB，避免读取大文件拖慢分析。
- `build_tree()` 生成最多 3 层、最多 220 个条目的目录树。
- `detect_stack()` 根据 `package.json`、`requirements.txt`、`pyproject.toml`、`go.mod`、`Cargo.toml` 等识别技术栈。
- `find_entrypoints()` 识别常见入口文件，如 `main.py`、`app.py`、`index.js`、`main.ts`、`App.vue`。
- `extract_symbols()` 用正则提取常见语言里的函数、类、导出函数和变量。
- `search_code()` 在问答 fallback 和 Agent 工具中用于关键词搜索，返回 `file:line` 片段。

这里的扫描是“轻量静态分析”，优点是快、依赖少、可测试；缺点是不能完整理解复杂调用图，也不能替代语言服务或 AST 分析。

## 8. LLM 报告与 fallback

LLM 配置在 `backend/app/config.py`：

- `DEEPSEEK_API_KEY`：配置后启用 DeepSeek-compatible API。
- `deepseek_base_url`：默认 `https://api.deepseek.com`。
- `deepseek_model`：默认 `deepseek-chat`。

`llm.get_llm()` 使用 `ChatOpenAI`，但传入 DeepSeek 的 base URL，因此可以接入兼容 OpenAI Chat Completions 形式的模型服务。

报告生成有两条路径：

1. 已配置 `DEEPSEEK_API_KEY`：
   - `generate_llm_report()` 调用 LLM。
   - prompt 要求输出中文 Markdown，覆盖项目概述、技术栈、目录结构、核心模块、数据流、设计模式、阅读路线等。
   - prompt 明确要求路径必须来自扫描结果，不能编造。

2. 未配置 `DEEPSEEK_API_KEY`：
   - `generate_llm_report()` 返回 `None`。
   - `analyze_project_stream()` 改用 `local_report()`。
   - 本地报告基于扫描摘要生成，确定性强，方便开发和测试。

问答也有 fallback：

- 有 LLM key 时，`create_code_agent()` 创建 LangChain Agent。
- Agent 拥有三个工具：`list_tree`、`read_file`、`search_repo`。
- 无 LLM key 时，`chat_stream()` 会从用户问题中提取关键词，调用本地 `search_code()`，把命中的文件行号作为可验证答案返回。

安全边界也在这里体现：`read_repo_file()` 会把目标路径 resolve 后检查是否仍在仓库根目录内，拒绝读取仓库外文件。

## 9. 前端交互与数据流

前端主体在 `frontend/src/App.vue`，使用 Vue Composition API 管理状态：

- `repoUrl`：当前输入的仓库地址。
- `activeProject`：当前查看或分析的项目。
- `projects`：左侧历史项目列表。
- `progress`：SSE 进度日志。
- `loading` / `asking`：分析和问答的忙碌状态。
- `chatMessages`：问答消息列表。
- `sourceTree` / `sourceFile`：源码浏览目录树和当前预览文件。
- `error`：当前错误提示。

几个关键 computed：

- `reportHtml`：把 Markdown 报告转换为 HTML，并用 DOMPurify 清洗。
- `isReady`：当前项目是否可以问答。
- `activeStepKey` / `activeStepIndex` / `progressPercent`：根据事件日志和项目状态计算进度条。
- `statusLabel`：把后端状态映射为中文展示。

主要交互：

1. `createAndAnalyze()`
   - POST 创建项目。
   - 写入 `activeProject`。
   - 添加 `connect` 进度。
   - 调用 `streamAnalysis()` 建立分析 SSE。

2. `streamAnalysis(projectId)`
   - 用 `EventSource` 监听分析事件。
   - `done` 后拉取项目详情，刷新列表。
   - `failed` 和 `onerror` 会关闭连接并展示错误。

3. `loadProject(project)`
   - 从列表加载历史项目详情。
   - 把进度设置为缓存命中提示。

4. `togglePinned(project)` / `deleteProject(project)`
   - 调用置顶或删除 API。
   - 删除前使用 Naive UI 的确认弹窗。

5. `askQuestion()`
   - 用 POST 发起问答流。
   - 通过 `ReadableStream` 手动解析 SSE。
   - 收到 `token` 后增量追加到 assistant 消息。

6. 源码浏览
   - 项目 `ready` 后，前端调用 `/source/tree` 加载可预览目录。
   - 用户点击文件时调用 `/source/file?path=...` 读取内容。
   - 后端只返回文本源码/配置文件，并限制单文件大小，避免把二进制或超大文件塞到页面。
   - 路径会经过仓库根目录校验，拒绝 `../` 这类越界读取。

前端报告和 assistant 回答都走 Markdown 渲染，这让报告结构和代码块更易读；DOMPurify 则降低直接插入 HTML 的 XSS 风险。

## 10. 测试策略

项目测试集中在后端，重点是把外部依赖隔离掉：

- 不依赖真实 GitHub 克隆。
- 不依赖真实 LLM 调用。
- 不依赖本机已有缓存。

主要测试文件：

- `backend/tests/unit/test_repository.py`
  - URL 规范化。
  - 非法协议、非允许 host、缺少 owner/repo 的错误处理。
  - 项目 ID 稳定性和项目名提取。

- `backend/tests/unit/test_database.py`
  - upsert、查询、列表、保存报告。
  - 已存在项目更新时保留旧报告和状态。
  - 置顶排序和删除。

- `backend/tests/unit/test_source_scan.py`
  - 技术栈、入口、符号识别。
  - 忽略 `node_modules`。
  - 代码搜索和目录树深度限制。
  - 源码浏览目录树、文件读取和路径越界拒绝。

- `backend/tests/unit/test_analyzer.py`
  - SSE 帧格式。
  - 本地报告内容。
  - 无 LLM key 的问答 fallback。
  - Agent 流式增量输出。
  - 同一项目并发分析通过锁串行化，避免重复 clone。

- `backend/tests/unit/test_llm.py`
  - `read_repo_file()` 防止路径穿越。
  - 仓库内文件读取正常。

- `backend/tests/e2e/test_api_core_flow.py`
  - 从创建项目、分析、缓存命中、问答、列表、置顶到删除的完整 API 链路。
  - 覆盖源码目录树、文件读取和分析完成前禁止浏览源码。
  - 通过 monkeypatch 替换 clone 和 LLM，保证测试稳定。

推荐命令见 `TESTING_CHECKLIST.md`：

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

```bash
cd frontend
npm install
npm run build
```

改动建议：

- 修改 URL、缓存、状态流转、SSE、fallback 行为时，优先补后端 unit 和 e2e 测试。
- 修改前端交互时，至少跑 `npm run build`，并手动验证创建任务、缓存加载、问答、删除确认。
- 涉及安全边界时，增加路径、host、输入为空、异常流的测试。

## 11. 当前设计亮点

- 核心流程清晰：创建项目和执行分析解耦，前端可以自然接入实时进度。
- 无 key 可运行：本地静态报告和本地搜索 fallback 让开发、演示和测试成本更低。
- 缓存简单有效：SQLite 足够轻量，适合单机开发工具。
- 扫描器可预测：基于文件系统、配置文件和正则，不需要复杂运行环境。
- 流式体验完整：分析用 `EventSource`，问答用 `fetch + ReadableStream`，分别适配 GET 和 POST 场景。
- 测试隔离较好：Git 和 LLM 都可以 monkeypatch，避免外部网络导致测试不稳定。

## 12. 需要注意的风险

- `clone_or_update()` 对已有仓库执行 `reset --hard origin/HEAD`。这是针对缓存目录的合理做法，但不应把用户手写目录配置为 clone 目标。
- `source_scan.py` 是轻量正则扫描，对大型 monorepo、生成代码、多语言复杂入口的识别可能不完整。
- SSE 当前没有心跳包，长时间 LLM 调用在某些代理或网关下可能遇到连接超时。
- SQLite 适合本地单用户或轻量使用；如果未来变成多用户服务，需要重新考虑并发、权限隔离和数据生命周期。
- Agent 回答依赖工具读取结果，但 LLM 仍可能表达过度确定。回答中应持续强调“基于当前读取到的源码”。
- 当前允许跨域 `allow_origins=["*"]`，适合本地演示；生产环境需要收紧。

## 13. 后续演进建议

可以按优先级逐步演进：

1. 更强的扫描能力
   - 对 Python、JavaScript/TypeScript 引入 AST 或语言服务，提取更准确的 import、路由、类方法和调用关系。
   - 为常见框架增加专项识别，例如 FastAPI route、Vue components、Next.js app router。

2. 更稳的流式协议
   - 增加 SSE heartbeat。
   - 给事件增加统一字段，如 `timestamp`、`project_id`、`trace_id`。
   - 问答流可补充引用文件列表，方便前端展示“依据来源”。

3. 更细的缓存策略
   - 缓存仓库 HEAD commit，判断远端是否变化。
   - 支持“强制重新分析”。
   - 把扫描摘要、报告、问答历史拆表保存，便于后续检索和版本比较。

4. 更好的前端体验
   - 报告目录导航和章节锚点。
   - 问答引用源码片段可点击跳转。
   - 源码浏览可以增加搜索、折叠目录、语法高亮和行号。
   - 分析失败时提供更具体的恢复动作，例如重试、清缓存、检查 key。

5. 多用户和安全
   - 增加认证和项目归属。
   - 限制 clone 大小、超时时间、允许 host、并发任务数。
   - 生产环境收紧 CORS 和文件读取边界。

6. 任务系统化
   - 把分析流程从请求生命周期中拆出，交给后台任务队列。
   - 前端通过任务 ID 订阅进度。
   - 避免长连接中断导致任务状态难恢复。

## 14. 新开发者阅读路线

建议按这个顺序读代码：

1. 先读 `README.md`，知道项目要解决的问题和运行方式。
2. 读 `backend/app/main.py`，看 API 如何组织。
3. 读 `backend/app/analyzer.py`，理解 clone、scan、summarize、cache、chat 的主流程。
4. 读 `backend/app/source_scan.py`，理解报告的数据来源。
5. 读 `backend/app/database.py` 和 `backend/app/repository.py`，理解缓存和本地仓库目录。
6. 读 `backend/app/llm.py`，理解 LLM 报告、Agent 工具和无 key fallback。
7. 读 `frontend/src/App.vue`，把后端事件和前端状态对应起来。
8. 最后读测试，尤其是 `backend/tests/e2e/test_api_core_flow.py`，它基本就是一份可执行的系统说明。

如果要做第一个小改动，建议从文案、报告章节、扫描识别规则或前端状态提示入手；如果要改核心链路，一定先补测试，再调整实现。
