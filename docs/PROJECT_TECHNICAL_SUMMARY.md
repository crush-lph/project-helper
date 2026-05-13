# Project-Helper 技术架构总结

> AI 驱动的源码分析与智能问答平台 — 简历技术描述参考

---

## 项目概述

基于 LangGraph + LangChain + FastAPI 构建的源码分析 Agent 系统。用户输入 GitHub 仓库链接，系统自动克隆、静态扫描、生成结构化分析报告，并支持基于 Agent 的多轮代码问答。全链路 SSE 流式输出，前端 Vue 3 实现代码浏览器（语法高亮、代码折叠、行级批注）。

---

## 核心技术栈

| 层级 | 技术 |
|------|------|
| Agent 框架 | LangGraph `create_react_agent` (ReAct) + LangChain `ChatOpenAI` |
| 状态管理 | LangGraph `MemorySaver` Checkpointer (per-thread 持久化) |
| LLM | DeepSeek API (OpenAI-compatible) |
| 后端 | FastAPI + Pydantic + anyio + SQLite (WAL) |
| 前端 | Vue 3 Composition API + highlight.js + DOMPurify |
| 流式协议 | SSE (Server-Sent Events), `astream_events` v2 |
| 可观测性 | LangChain `BaseCallbackHandler` 自定义指标采集 |

---

## 1. LangGraph Agent 架构

### 1.1 Agent 构建

使用 LangGraph 的 `create_react_agent` 构建 ReAct 模式 Agent，替代 LangChain legacy `AgentExecutor`：

```python
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

_checkpointer = MemorySaver()

def create_code_agent(settings, root_path):
    llm = get_llm(settings, streaming=True)
    tools = _build_tools(root_path)
    system_prompt = _prompts.get("agent_system_prompt")

    return create_react_agent(
        llm, tools,
        prompt=system_prompt,
        checkpointer=_checkpointer,
    )
```

**设计决策：**
- `create_react_agent` 内置 ReAct 循环（思考 → 调工具 → 观察 → 再思考），无需手动编排
- `MemorySaver` 作为 Checkpointer，通过 `thread_id` 隔离不同项目的对话状态
- Agent 实例可安全并发复用，不再每次请求重建（LLM + Tools + Prompt）

### 1.2 Tool 设计

3 个 `@tool` 装饰器函数，闭包绑定 `root_path`：

| Tool | 功能 | 约束 |
|------|------|------|
| `list_tree()` | 返回项目目录树（文本格式） | max 260 条目, depth 3 |
| `read_file(path)` | 按相对路径读取源码 | 24KB 上限, 路径穿越防护 |
| `search_repo(query)` | 全项目关键词搜索 | 30 条结果上限 |

**安全机制：** `read_repo_file()` 对所有文件读取做 `Path.resolve()` + `relative_to(root)` 校验，拒绝任何仓库外路径。

### 1.3 状态持久化与对话隔离

```
Thread ID = Project ID
    ├── 第1轮对话: [HumanMessage, AIMessage, ToolMessage, AIMessage]
    ├── 第2轮对话: [上述 + HumanMessage, AIMessage, ...]
    └── 第N轮对话: 完整历史自动保持，无需前端传递 history
```

**对比旧方案：**

| | 旧方案 (AgentExecutor) | 新方案 (LangGraph) |
|---|---|---|
| 状态管理 | 前端传递 history 数组 | Checkpointer 自动管理 |
| Agent 生命周期 | 每次请求重建 | 实例复用 |
| 上下文丢失风险 | 前端丢 history → Agent 失忆 | thread_id → 自动恢复 |
| 异步流式 | 手动 Thread + Queue (40行) | `astream_events` (3行) |

---

## 2. Harness Engineering — Agent 外围基础设施

Harness Engineering 不是 Agent 本身，而是让 Agent 可靠运行的支撑层。

### 2.1 可观测性 (`observability.py`)

自定义 `LLMCallLogger` 继承 LangChain `BaseCallbackHandler`，实现 7 个回调钩子：

```
on_llm_start    → 记录 prompt 长度, 递增调用计数, 记录 start time
on_llm_end      → 计算延迟, 提取 token usage, 记录完成
on_llm_error    → 计算延迟, 递增错误计数, 记录异常类型
on_tool_start   → 记录工具名和输入
on_tool_end     → 记录工具输出长度和延迟
on_tool_error   → 记录工具异常
on_agent_action → 记录 Agent 决策（调哪个工具、传什么参数）
```

**采集指标（7 维）：**

| 指标 | 含义 |
|------|------|
| `total_llm_calls` | LLM 调用总次数 |
| `total_llm_errors` | LLM 调用失败次数 |
| `total_tool_calls` | Tool 调用总次数 |
| `total_tool_errors` | Tool 调用失败次数 |
| `total_prompt_tokens` | 累计输入 Token |
| `total_completion_tokens` | 累计输出 Token |
| `total_latency_ms` | 累计延迟（毫秒） |

通过 `/api/metrics` 端点暴露为 JSON 快照。

**Stale Entry 淘汰机制：** `_MAX_PENDING = 128`，当 pending tracking entries 超过阈值时淘汰最早一半，防止长时间运行的内存泄漏。

**Token 提取双路径：** 先尝试 `llm_output.token_usage`（OpenAI 格式），再尝试 `generation.message.usage_metadata`（LangChain 格式），兜底返回 0。

### 2.2 安全防护 (`guardrails.py`)

**Prompt Injection 检测：** 10 条预编译正则（case-insensitive），覆盖：

| 类别 | 检测模式 |
|------|----------|
| 指令覆盖 | "ignore previous instructions", "disregard prior instructions" |
| 记忆清除 | "forget everything", "forget your instructions" |
| 角色劫持 | "you are now " |
| 伪造指令 | "new instructions:", "override ... instructions" |
| ChatML 注入 | `system:` at line start, `<|im_start|>system` |
| Llama 注入 | `[INST]...[/INST]` |

在 `chat_stream` 端点入口检测，命中即返回 HTTP 400。

**路径穿越防护（三层纵深）：**

```
Layer 1: safe_source_path()     → symlink 检测 (逐段 is_symlink())
Layer 2: read_repo_file()       → resolve() + relative_to(root) 二次校验
Layer 3: delete_project()       → 路径边界检查后才执行 shutil.rmtree
```

### 2.3 错误分类与优雅降级

**三级错误分类：**

```python
def classify_error(exc) -> tuple[str, str, Exception]:
    # "transient"  → 网络超时, 5xx, 文件系统错误, Git 网络故障
    # "rate_limit" → HTTP 429
    # "permanent"  → 4xx, Git 认证失败, 仓库不存在, 未知错误
```

每类映射为用户友好的中文提示，通过 SSE `failed` 事件推送给前端。

**三层 Fallback（报告生成）：**

```
Layer 1: llm.with_structured_output(ReportOutput, method="json_mode")
    ↓ 失败
Layer 2: raw prompt + JSON schema 附加 + _parse_report_output() 手动解析
    ↓ 失败
Layer 3: local_report() 确定性模板（无 LLM 时兜底）
```

### 2.4 并发控制

- 项目级 `asyncio.Lock`（`defaultdict[str, asyncio.Lock]`）防止同一项目并发分析
- `anyio.to_thread.run_sync` 将阻塞 I/O（git clone、文件扫描、LLM 调用）offload 到线程池，不阻塞 FastAPI 事件循环

---

## 3. Structured Output — LLM 输出格式保障

### 3.1 Pydantic Schema 定义

```python
class ReportSection(BaseModel):
    title: str = Field(description="章节标题")
    content: str = Field(description="章节内容（Markdown）")

class ReportOutput(BaseModel):
    overview: ReportSection
    tech_stack: ReportSection
    directory_structure: ReportSection
    core_modules: ReportSection
    data_flow: ReportSection
    design_patterns: ReportSection
    reading_path: ReportSection
    follow_up_questions: list[str]
```

### 3.2 输出格式化

```python
sections = [result.overview, result.tech_stack, ...]
body = "\n\n".join(f"## {s.title}\n\n{s.content}" for s in sections)
questions = "\n".join(f"- {q}" for q in result.follow_up_questions)
return f"{body}\n\n## 可以继续追问\n\n{questions}"
```

---

## 4. SSE 流式架构

### 4.1 协议格式

```
event: progress
data: {"step": "clone", "message": "正在克隆或更新仓库..."}

event: token
data: {"text": "这个项目的入口文件是..."}

event: agent
data: {"type": "action", "data": {"tool": "read_file", "input": {"path": "src/main.py"}}}

event: done
data: {}
```

### 4.2 分析管线流（GET SSE）

```
Client ──GET /api/projects/{id}/analyze/stream──► Server

Server 内部:
  analyze_project_stream() [async generator]
    ├── yield sse("progress", {"step": "clone"})     ← anyio.to_thread(clone_or_update)
    ├── yield sse("progress", {"step": "scan"})      ← anyio.to_thread(scan_repository)
    ├── yield sse("progress", {"step": "summarize"}) ← anyio.to_thread(generate_llm_report)
    └── yield sse("done", {"project_id": ...})
```

### 4.3 Agent 问答流（POST SSE）

```
Client ──POST /api/projects/{id}/chat/stream──► Server

Server 内部:
  _stream_agent_events() [async generator]
    └── agent.astream_events(input, config, version="v2")
          ├── on_chat_model_stream → yield sse("token", {"text": chunk})
          ├── on_tool_start       → yield sse("agent", {"type": "action", ...})
          └── on_tool_end         → yield sse("agent", {"type": "observation", ...})
```

---

## 5. 代码分析引擎 (`source_scan.py`)

### 5.1 静态扫描能力

| 能力 | 实现 |
|------|------|
| 技术栈检测 | 模式匹配 config 文件 (package.json, pyproject.toml, go.mod, Cargo.toml, pom.xml) + 扩展名统计 |
| 入口文件识别 | 已知文件名匹配 (main.py, app.py, server.py, index.js, etc.) |
| 符号提取 | 正则提取 def/class/function/const/let，每文件 12 个，总计 60 个 |
| 目录树构建 | 嵌套 JSON 结构（前端浏览器）+ 文本缩进树（Agent 工具） |
| 全文搜索 | 大小写不敏感逐行匹配，跨 1200 文件上限 |

### 5.2 安全约束

- 跳过 15 个目录（.git, node_modules, __pycache__, dist, build, .venv 等）
- 33 种文本文件扩展名 + 15 种配置文件名
- 单文件 350KB 上限，单次扫描 900 文件上限
- Symlink 逐段检测，拒绝任何符号链接

---

## 6. Prompt Engineering

### 6.1 Agent System Prompt（3 句约束）

```
1. 回答必须基于工具读取的源码，不得臆测
2. 优先使用 search_repo 搜索，再用 read_file 读取
3. 用中文回答，附带文件路径和下一步阅读建议
```

### 6.2 Report Prompt（结构化输出约束）

- 7 个必填段落（概述、技术栈、目录结构、核心模块、数据流、设计模式、阅读路线）
- 严格 JSON 格式输出，每段 title + content
- 约束："语言通俗但准确"、"不确定推断需明确标注"、"文件路径必须来自扫描结果，不得编造"

### 6.3 PromptManager

```python
class PromptManager:
    def get(name) -> str:       # 加载并缓存 .md 模板
    def render(name, **kw) -> str:  # str.format() 变量替换
    def clear_cache():           # 强制重新加载
```

模板外部化为 `.md` 文件，支持版本控制和独立测试。

---

## 7. 前端架构

### 7.1 流式消费

- **分析流**：`EventSource`（原生 SSE，GET 请求）
- **聊天流**：`fetch()` + `ReadableStream` reader（POST 请求，`AbortController` 支持中止）

### 7.2 并发竞态处理

Token 机制：每次新请求递增 token，响应返回时检查 token 是否过期，过期则丢弃。

```javascript
const chatStreamToken = ref(0)
async function askQuestion() {
    const token = ++chatStreamToken.value
    // ... fetch ...
    if (token !== chatStreamToken.value) return  // 过期，丢弃
}
```

### 7.3 代码浏览器

- **语法高亮**：highlight.js + DOMPurify XSS 防护
- **Tag-aware 行分割**：自定义 `splitHighlightedHtml()` 处理跨行 `<span>` 标签
- **双策略代码折叠**：
  - 缩进折叠（Python, YAML）— 栈追踪缩进层级
  - 花括号折叠（JS, TS, JSON, CSS）— 栈追踪 `{` 位置，跳过注释
- **行级批注**：CRUD + jump-to-line (`scrollIntoView`) + 行计数徽章

---

## 关键技术关键词

```
LangGraph, LangChain, ReAct Agent, Tool Calling, Checkpointer, MemorySaver,
astream_events, Structured Output, JSON Mode, Pydantic Schema,
Prompt Engineering, Prompt Injection Detection, Defense in Depth,
Harness Engineering, Observability, LLM Metrics, Callback Handler,
SSE, Streaming, Async Generator, FastAPI, anyio, Thread Offloading,
Error Classification, Graceful Degradation, Fallback Strategy,
Path Traversal Prevention, Symlink Detection, Concurrent Lock,
Vue 3, Composition API, highlight.js, DOMPurify, XSS Prevention,
SQLite, WAL Mode, GitPython, Shallow Clone
```
