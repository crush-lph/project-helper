"""
分析编排模块 —— 项目的"大脑"，协调克隆、扫描、报告、问答的全流程

这个模块做什么？
  1. analyze_project_stream()：分析流水线（克隆 → 扫描 → 生成报告 → 缓存）
  2. chat_stream()：问答流水线（用户问题 → Agent 推理 → 流式输出答案）
  3. 两个函数都返回 SSE 事件流，前端通过 EventSource 或 fetch 接收。

前端类比：
  这个文件就像前端的 useProjectHelper composable 的后端对应物。
  - analyze_project_stream() 对应 streamAnalysis()
  - chat_stream() 对应 askQuestion()
  - 两者都用 SSE（Server-Sent Events）向前端推送实时进度。

Python 知识点 —— async def（异步函数）：
  async def 表示这个函数是"异步的"，内部可以用 await。
  类似 JS 的 async function。
  Python 的异步基于 asyncio 库，和 JS 的事件循环原理类似。
  但 Python 需要显式用 async/await，而 JS 的很多 API 天生就是 Promise。

Python 知识点 —— AsyncGenerator（异步生成器）：
  async def xxx() -> AsyncGenerator[str, None]:
      yield "a"
      yield "b"
  异步生成器可以"暂停"和"恢复"执行，每次 yield 一个值。
  前端没有直接对应，但可以理解为"能 await 的 generator"。
  前端最接近的概念是 ReadableStream 的 controller.enqueue()。
"""

from __future__ import annotations

import asyncio     # Python 的异步 IO 库，类似 JS 的 Promise + 事件循环
import json        # JSON 序列化
import threading   # 线程（用于把同步的 LangChain Agent 桥接到异步世界）
from collections import defaultdict  # 带默认值的字典
from pathlib import Path
from typing import Any, AsyncGenerator  # 类型标注

import anyio       # 跨平台异步库，提供 run_sync（在异步函数中运行同步代码）
import httpx       # HTTP 客户端（LangChain 依赖它，我们也用它做错误分类）

from .config import Settings
from .database import Database
from .llm import create_code_agent, generate_llm_report
from .repository import clone_or_update
from .source_scan import scan_repository, search_code


def classify_error(exc: Exception) -> tuple[str, str]:
    """
    异常分类器 —— 把技术错误翻译成用户友好的消息。

    返回 (error_type, user_message) 元组。

    Python 知识点 —— isinstance()：
      isinstance(exc, httpx.TimeoutException)
      判断 exc 是否是 TimeoutException 类型（或其子类）。
      类似 JS 的 exc instanceof TimeoutException。
      Python 支持多类型判断：isinstance(exc, (TypeA, TypeB))

    Python 知识点 —— tuple（元组）：
      tuple[str, str] 表示"固定长度、固定类型的序列"。
      类似 TS 的 [string, string]。
      和 list 的区别：tuple 不可变（创建后不能修改）。
      用 (a, b) 创建，用 a, b = some_tuple 解包。
    """
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
        return "transient", "网络连接超时，请稍后重试。"
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code == 429:
            return "rate_limit", "API 请求频率超限，请稍后重试。"
        if exc.response.status_code >= 500:
            return "transient", "API 服务暂时不可用，请稍后重试。"
        return "permanent", f"API 请求失败：{exc.response.status_code}"
    if isinstance(exc, (OSError, PermissionError)):
        return "transient", f"文件系统错误：{exc}"
    return "permanent", f"未知错误：{exc}"


def local_report(repo_url: str, summary: dict[str, Any]) -> str:
    """
    本地静态报告生成（不需要 LLM）。

    当没有配置 API key 时，用扫描结果直接拼接一个基础报告。
    这保证了即使没有 LLM，应用也能基本可用。

    Python 知识点 —— f-string（格式化字符串）：
      f"text {variable} more text"
      类似 JS 的 `text ${variable} more text`
      但用 {} 而不是 ${}。f-string 是 Python 3.6+ 的特性。

    Python 知识点 —— 生成器表达式：
      "、".join(item for item in list)
      (item for item in list) 是生成器表达式，类似 JS 的 list.map()，
      但它是"惰性"的：不会一次性创建整个数组，而是逐个产生值。
      .join() 把它们拼接成字符串，用 "、" 分隔。
      类似 JS 的 list.join("、")

    Python 知识点 —— or 用于默认值：
      summary.get("stack") or ["暂未从配置文件中明确识别"]
      如果 get() 返回 None 或空列表（falsy），用 or 后面的值。
      类似 JS 的 summary.stack ?? ["暂未从配置文件中明确识别"]
    """
    stack = "、".join(summary.get("stack") or ["暂未从配置文件中明确识别"])
    entrypoints = "\n".join(f"- `{item}`" for item in summary.get("entrypoints", [])) or "- 暂未识别到典型入口文件"
    core_files = "\n".join(f"- `{item}`" for item in summary.get("core_files", [])[:18])
    symbols = "\n".join(f"- `{item}`" for item in summary.get("symbols", [])[:24]) or "- 暂未提取到明显函数/类符号"
    extensions = ", ".join(f"{key}: {value}" for key, value in summary.get("extensions", {}).items())
    readme = (summary.get("readme") or "").strip().splitlines()
    # splitlines() 按行分割字符串，类似 JS 的 .split("\n")
    readme_hint = "\n".join(f"> {line[:180]}" for line in readme[:8]) if readme else "> 该仓库没有可读取的 README 摘要。"

    return f"""# project-helper 源码分析报告

## 项目概述

仓库：`{repo_url}`

从当前扫描结果看，这个项目一共有 **{summary.get("file_count", 0)}** 个可读源码/配置文件。新手可以先把它理解成三层：入口文件负责启动，核心目录承载业务逻辑，配置文件说明它依赖什么技术和怎样运行。

README 片段：

{readme_hint}

## 技术栈

识别到的主要技术：**{stack}**。

文件类型分布：`{extensions}`。

## 目录结构

```text
{summary.get("tree", "")}
```

## 核心入口

{entrypoints}

## 核心模块与重要文件

{core_files}

## 关键函数/类线索

{symbols}

## 数据流怎么读

1. 先找入口文件，看程序如何启动、路由如何注册、主流程如何接线。
2. 再看配置文件，例如 `package.json`、`pyproject.toml`、`requirements.txt`、`go.mod`，确认外部依赖。
3. 顺着入口引用到的模块往下读：路由/命令入口 -> service/usecase -> 数据访问/工具函数。
4. 遇到不懂的函数名，回到 project-helper 的问答区搜索它，让 Agent 帮你定位调用链。

## 设计模式与工程实践

从静态扫描推断，这个仓库可能采用了按目录分层、入口和业务逻辑分离、配置驱动依赖管理等常见工程实践。更细的模式需要结合具体文件继续阅读验证。

## 新手阅读路线

1. 阅读 README，先知道项目"解决什么问题"。
2. 打开入口文件，理解程序第一步做什么。
3. 浏览核心目录，不急着逐行看，先建立地图。
4. 挑一个功能，从路由/命令开始追到核心函数。
5. 用问答区提问，例如"用户请求从哪里进入？"、"某个配置项在哪里使用？"。

## 可以继续追问

- 这个项目启动流程是什么？
- 某个 API/命令的调用链是什么？
- 哪些文件最值得先读？
- 如果我要改一个功能，应该从哪里下手？
"""


def sse(event: str, data: dict[str, Any]) -> str:
    """
    格式化一条 SSE 事件。

    SSE 协议格式：
      event: 事件名\n
      data: JSON 数据\n
      \n（空行表示事件结束）

    前端接收方式：
      const events = new EventSource('/api/projects/123/analyze/stream')
      events.addEventListener('progress', (e) => console.log(JSON.parse(e.data)))
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---- 并发控制 ----
# defaultdict 是"带默认值的字典"，访问不存在的键时自动创建默认值。
# 这里默认值是 asyncio.Lock()（异步锁）。
# 前端类比：类似用 Map 实现的锁机制，防止同一项目被同时分析。
_analysis_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def iter_agent_stream(agent, question: str) -> AsyncGenerator[dict[str, Any], None]:
    """
    把同步的 LangChain Agent 桥接为异步生成器。

    为什么需要这个？
      LangChain 的 agent.stream() 是同步的（会阻塞当前线程）。
      但我们的 FastAPI 是异步的（用 async/await）。
      如果直接调用 agent.stream()，会阻塞整个事件循环，其他请求都会卡住。

    解决方案：
      在一个新线程中运行同步的 agent.stream()，
      通过 asyncio.Queue 把结果传回异步世界。

    前端类比：
      就像在 Web Worker 中运行耗时计算，通过 postMessage 把结果传回主线程。

    Python 知识点 —— asyncio.Queue：
      异步安全的队列。await queue.get() 会"暂停"当前协程，
      直到有数据可读（不阻塞事件循环）。
      类似 JS 的 ReadableStream 或 MessageChannel。

    Python 知识点 —— threading.Thread：
      创建一个新线程运行函数。daemon=True 表示"守护线程"：
      主线程退出时，守护线程自动终止（不会阻止进程退出）。

    Python 知识点 —— loop.call_soon_threadsafe()：
      从非异步线程安全地调度一个回调到事件循环。
      因为 asyncio.Queue.put_nowait() 只能在事件循环所在的线程调用，
      所以需要用 call_soon_threadsafe 来安全地调用它。
    """
    loop = asyncio.get_running_loop()  # 获取当前事件循环
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    def run_agent() -> None:
        """在新线程中运行同步的 Agent，把结果放进队列。"""
        try:
            for step in agent.stream({"input": question}):
                # call_soon_threadsafe 确保 put_nowait 在事件循环线程执行
                loop.call_soon_threadsafe(queue.put_nowait, ("step", step))
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

    threading.Thread(target=run_agent, daemon=True).start()

    # 从队列中读取结果，yield 给调用方
    while True:
        kind, payload = await queue.get()  # 等待（不阻塞事件循环）
        if kind == "step":
            yield payload  # yield 把值传给调用方，然后暂停等待下一次 next()
        elif kind == "error":
            raise payload  # 把异常重新抛出
        else:  # "done"
            return  # 结束生成器


async def analyze_project_stream(db: Database, settings: Settings, project: dict[str, Any]) -> AsyncGenerator[str, None]:
    """
    分析流水线 —— 克隆 → 扫描 → 生成报告 → 缓存。

    这是一个"异步生成器"：每次 yield 一条 SSE 事件，前端实时显示进度。

    Python 知识点 —— async with（异步上下文管理器）：
      async with _analysis_locks[project_id]:
          ...  # 在锁保护下执行
      类似 JS 的 async mutex.lock() / unlock()。
      async with 保证即使发生异常，锁也会被正确释放。

    Python 知识点 —— await anyio.to_thread.run_sync(fn, *args)：
      在线程池中运行同步函数 fn，不阻塞事件循环。
      类似 JS 的 new Promise(resolve => setTimeout(() => resolve(fn(...))))
      但更高效，用的是真正的线程池。

    Python 知识点 —— return 在生成器中：
      在 async generator 中，return 表示"结束生成器"（不再 yield 更多值）。
      类似 JS generator 的 return()。
    """
    project_id = project["id"]

    # 加锁：同一项目同时只能有一个分析任务在运行
    async with _analysis_locks[project_id]:
        # 重新读取项目状态（可能在等锁期间被其他请求更新了）
        current_project = db.get_project(project_id) or project

        # 缓存命中：如果已经分析过，直接返回缓存结果
        if current_project["status"] == "ready" and current_project.get("report"):
            yield sse("cached", {"message": "命中缓存，直接返回上次分析结果。", "project_id": project_id})
            yield sse("done", {"project_id": project_id})
            return

        root = Path(current_project["local_path"])
        try:
            # 第 1 步：克隆或更新仓库
            db.update_status(project_id, "cloning")
            yield sse("progress", {"step": "clone", "message": "正在克隆或更新仓库..."})
            # clone_or_update 是同步阻塞操作，用 run_sync 放到线程池执行
            await anyio.to_thread.run_sync(clone_or_update, current_project["repo_url"], root)

            # 第 2 步：扫描源码
            db.update_status(project_id, "scanning")
            yield sse("progress", {"step": "scan", "message": "正在扫描目录、技术栈和核心文件..."})
            summary = await anyio.to_thread.run_sync(scan_repository, root)

            # 第 3 步：生成报告（LLM 或本地静态）
            db.update_status(project_id, "summarizing")
            yield sse("progress", {"step": "summarize", "message": "正在生成通俗版源码报告..."})
            report = await anyio.to_thread.run_sync(generate_llm_report, settings, current_project["repo_url"], summary)

            if report is None:
                # LLM 不可用，使用本地静态报告
                report = local_report(current_project["repo_url"], summary)
                summary["llm"] = "DEEPSEEK_API_KEY 未配置，已使用本地静态分析生成报告。"
            else:
                summary["llm"] = f"DeepSeek model: {settings.deepseek_model}"

            # 保存到数据库
            db.save_analysis(project_id, report, summary)
            yield sse("done", {"project_id": project_id})

        except Exception as exc:
            # 统一错误处理：分类错误，更新状态，返回用户友好的消息
            error_type, message = classify_error(exc)
            db.update_status(project_id, "failed")
            yield sse("failed", {"message": message, "error_type": error_type})


async def chat_stream(settings: Settings, project: dict[str, Any], question: str) -> AsyncGenerator[str, None]:
    """
    问答流水线 —— 用户问题 → Agent 推理 → 流式输出答案。

    Python 知识点 —— lambda（匿名函数）：
      lambda: search_code(root, query, limit=12)
      创建一个简短的匿名函数，类似 JS 的 () => searchCode(root, query, 12)
      常用于"只需要用一次"的简单函数。
    """
    root = Path(project["local_path"])
    agent = create_code_agent(settings, str(root))

    if agent is None:
        # 没有 LLM，使用本地关键词搜索作为降级方案
        yield sse("token", {"text": "当前未配置 DEEPSEEK_API_KEY，我先用本地搜索给你一个可验证答案。\n\n"})

        # 提取问题中的关键词（简单的分词策略）
        # replace("，", " ") 把中文逗号替换为空格，方便按空格分割
        keywords = [part for part in question.replace("，", " ").replace("？", " ").split() if len(part) >= 2]
        query = keywords[0] if keywords else question[:20]  # 取第一个关键词，或截取问题前 20 字符

        # lambda 用于包装同步调用，让 anyio 能在线程池中执行
        hits = await anyio.to_thread.run_sync(lambda: search_code(root, query, limit=12))
        answer = f"我搜索了关键词 `{query}`，找到这些线索：\n\n```text\n{hits}\n```\n\n建议你继续追问一个更具体的问题，例如「解释第一个文件的作用」或「沿着这个函数追调用链」。"

        # 逐行输出（模拟流式效果）
        for chunk in answer.splitlines(keepends=True):
            yield sse("token", {"text": chunk})
        yield sse("done", {})
        return

    # 有 LLM，使用 Agent 推理
    try:
        async for step in iter_agent_stream(agent, question):
            # 根据 step 的内容判断 Agent 在做什么
            text = ""
            if "actions" in step:
                # Agent 决定调用工具
                action_names = ", ".join(action.tool for action in step["actions"])
                text = f"正在调用工具：{action_names}"
            elif "steps" in step:
                # Agent 读取了工具返回的结果
                text = "已读取相关源码片段。"
            elif "output" in step:
                # Agent 生成了最终答案
                text = str(step["output"])

            if text:
                yield sse("token", {"text": text + "\n"})
        yield sse("done", {})
    except Exception as exc:
        _, message = classify_error(exc)
        yield sse("failed", {"message": message})
