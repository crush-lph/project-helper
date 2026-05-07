"""
LLM 集成模块 —— 连接 DeepSeek 大模型 + 构建问答 Agent

这个模块做什么？
  1. 创建 LLM 客户端（连接 DeepSeek API）
  2. 生成分析报告（用 LLM 把扫描结果写成通俗的中文报告）
  3. 创建问答 Agent（LLM + 工具 = 能读源码的智能助手）

前端类比：
  这个文件相当于前端的 API 客户端 + 业务逻辑层。
  - get_llm()        → 创建 axios 实例（配置 base URL、超时、重试）
  - build_report_prompt() → 构建请求体
  - generate_llm_report() → 发送请求并处理响应
  - create_code_agent()   → 创建带工具调用能力的 AI Agent

LangChain 核心概念：
  - ChatOpenAI：LLM 的客户端（兼容 OpenAI API 的 DeepSeek 也能用）
  - @tool：把普通函数注册为 Agent 可调用的工具
  - AgentExecutor：Agent 的运行时，负责"思考 → 调工具 → 再思考"的循环
  - create_tool_calling_agent：创建能调用工具的 Agent

Python 知识点 —— 模块导入：
  from .config import Settings
  .config 表示"当前包（同一目录）下的 config 模块"。
  类似 JS 的 import { Settings } from './config'
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain.tools import tool          # 工具装饰器，把函数变成 Agent 可调用的工具
from langchain_openai import ChatOpenAI   # OpenAI 兼容的 LLM 客户端（DeepSeek 也能用）

from .config import Settings
from .observability import LLMCallLogger       # 我们自定义的日志记录器
from .prompts.manager import PromptManager     # prompt 模板管理器
from .source_scan import read_text, search_code  # 源码扫描工具函数

# ---- 模块级单例 ----
# 这些变量在模块导入时就创建好，整个应用共享同一份。
# 类似 JS 模块顶层的 const client = new SomeClient()
_prompts = PromptManager()      # prompt 模板管理器
_llm_logger = LLMCallLogger()   # LLM 调用日志记录器


def get_llm(settings: Settings, streaming: bool = False) -> ChatOpenAI | None:
    """
    创建 LLM 客户端实例。

    参数：
      settings:  应用配置（包含 API key、base URL、模型名等）
      streaming: 是否启用流式输出（逐字返回，类似 SSE）

    返回：
      ChatOpenAI 实例，或者 None（如果没有配置 API key）

    前端类比：
      这就像创建一个配置好的 axios 实例：
        const client = axios.create({
          baseURL: settings.deepseekBaseURL,
          timeout: settings.llmTimeout,
          headers: { Authorization: `Bearer ${apiKey}` }
        })

    Python 知识点 —— 函数返回类型：
      -> ChatOpenAI | None
      表示"返回 ChatOpenAI 实例或 None"。
      | 是联合类型语法（Python 3.10+），类似 TS 的 ChatOpenAI | null。

    Python 知识点 —— 提前返回（guard clause）：
      if not settings.deepseek_api_key:
          return None
      如果没有 API key，直接返回 None，不创建客户端。
      这比在调用方每次都检查 API key 更简洁。
    """
    if not settings.deepseek_api_key:
        return None

    return ChatOpenAI(
        api_key=settings.deepseek_api_key,       # API 密钥
        base_url=settings.deepseek_base_url,     # API 地址（DeepSeek 用 OpenAI 兼容格式）
        model=settings.deepseek_model,           # 模型名
        temperature=0.2,                          # 温度：越低越确定（0=确定性，1=创造性）
        streaming=streaming,                      # 是否流式输出
        max_retries=settings.llm_max_retries,    # 失败重试次数
        request_timeout=settings.llm_timeout,     # 单次请求超时秒数
        callbacks=[_llm_logger],                  # 注册日志回调（自动记录每次调用）
    )
    # ChatOpenAI 的参数类似 axios.create() 的 config：
    #   max_retries  → axios 的 retry 配置
    #   request_timeout → axios 的 timeout
    #   callbacks    → axios 的 interceptors（拦截器）


def build_report_prompt(repo_url: str, summary: dict[str, Any]) -> str:
    """
    构建报告生成的 prompt。

    把仓库 URL 和扫描结果填入 prompt 模板。
    前端类比：就像用模板字符串构建 API 请求体。
    """
    return _prompts.render("report_prompt", repo_url=repo_url, summary=summary)


def generate_llm_report(settings: Settings, repo_url: str, summary: dict[str, Any]) -> str | None:
    """
    用 LLM 生成源码分析报告。

    返回报告文本，或者 None（如果 LLM 不可用）。

    Python 知识点 —— llm.invoke()：
      invoke() 是 LangChain 的标准调用方法，发送 prompt 给 LLM 并等待响应。
      类似 await fetch(url, { body: prompt })。
      response.content 是 LLM 返回的文本内容。
    """
    llm = get_llm(settings)
    if llm is None:
        return None  # 没有 API key，返回 None 让调用方使用本地报告
    response = llm.invoke(build_report_prompt(repo_url, summary))
    return str(response.content)


def read_repo_file(root_path: str, path: str, max_chars: int = 24_000) -> str:
    """
    安全地读取仓库中的文件。

    这个函数做了路径遍历防护：
      如果用户传入 "../../etc/passwd"，resolve() 会解析为绝对路径，
      然后检查是否在 root 目录内。如果不在，拒绝读取。

    前端类比：就像后端 API 的文件下载接口要做路径校验，防止用户下载 /etc/passwd。

    Python 知识点 —— Path.resolve()：
      把相对路径转为绝对路径，并解析所有符号链接和 ".."。
      类似 Node.js 的 path.resolve() 或 fs.realpathSync()。
    """
    root = Path(root_path).resolve()           # 解析为绝对路径
    target = (root / path).resolve()           # 拼接并解析用户传入的路径
    try:
        target.relative_to(root)               # 检查 target 是否在 root 下
    except ValueError:                          # 如果不在，relative_to 会抛出 ValueError
        return "拒绝读取仓库之外的文件。"
    if not target.exists() or not target.is_file():
        return "文件不存在。"
    return read_text(target, max_chars=max_chars)


def create_code_agent(settings: Settings, root_path: str):
    """
    创建源码问答 Agent。

    Agent = LLM + 工具 + 推理循环。
    它能"思考"用户的问题，决定调用哪个工具，根据工具结果继续思考，直到得出答案。

    前端类比：
      Agent 就像一个自动化脚本：
        1. 接收用户问题
        2. 思考："我需要先搜索一下"
        3. 调用 search_repo 工具
        4. 看到结果，思考："让我读一下这个文件"
        5. 调用 read_file 工具
        6. 看到内容，思考："现在我可以回答了"
        7. 输出最终答案

    Python 知识点 —— @tool 装饰器：
      装饰器是 Python 的语法糖，用 @ 符号放在函数定义前面。
      @tool 把一个普通函数变成 LangChain 可识别的"工具"。
      类似 JS 的高阶函数：const enhanced = decorator(originalFn)

      前端等价概念：
        // JS 中类似的装饰器模式
        @registerTool({ description: "..." })
        function listTree() { ... }

    Python 知识点 —— 内部函数（闭包）：
      list_tree、read_file、search_repo 定义在 create_code_agent 内部，
      它们可以访问外部函数的参数 root_path（闭包捕获）。
      类似 JS 中函数内部定义的函数可以访问外部变量。
    """
    llm = get_llm(settings, streaming=True)
    if llm is None:
        return None

    # 动态导入（只在需要时导入，避免在无 LLM 模式下加载不需要的依赖）
    try:
        from langchain.agents import AgentExecutor, create_tool_calling_agent
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    except ImportError:
        return None  # 如果 LangChain 组件不可用，返回 None

    # ---- 定义 Agent 可调用的三个工具 ----

    @tool
    def list_tree() -> str:
        """List the repository directory tree that has already been summarized."""
        # docstring 会被 LangChain 用作工具描述，告诉 Agent 这个工具能做什么
        from .source_scan import build_tree
        return build_tree(Path(root_path), max_entries=260)

    @tool
    def read_file(path: str) -> str:
        """Read a source file by repository-relative path."""
        return read_repo_file(root_path, path)

    @tool
    def search_repo(query: str) -> str:
        """Search source files for a keyword and return file:line snippets."""
        return search_code(Path(root_path), query, limit=30)

    # ---- 构建 Agent ----

    system_prompt = _prompts.get("agent_system_prompt")
    tools = [list_tree, read_file, search_repo]

    # ChatPromptTemplate 定义了发给 LLM 的消息结构。
    # 类似前端构建 API 请求体：
    #   { messages: [systemMsg, userMsg, ...agentScratchpad] }
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),              # 系统消息：定义 Agent 的角色和规则
        ("human", "{input}"),                    # 用户消息：{input} 会被替换为实际问题
        MessagesPlaceholder("agent_scratchpad"), # Agent 的思考过程（工具调用记录）
    ])

    # create_tool_calling_agent 把 LLM + 工具 + prompt 组合成一个 Agent
    agent = create_tool_calling_agent(llm, tools, prompt)

    # AgentExecutor 是 Agent 的运行时，负责执行"思考 → 调工具 → 再思考"的循环
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,             # 不在控制台打印详细推理过程
        max_iterations=8,          # 最多推理 8 轮（防止死循环）
        max_execution_time=60,     # 最多执行 60 秒（防止卡死）
    )
    # max_iterations 和 max_execution_time 是安全阀：
    #   如果 Agent 陷入循环（反复调用同一工具），最多 8 轮或 60 秒后强制停止。
    #   前端类比：就像 setTimeout(fn, 60000) 作为超时保护。
