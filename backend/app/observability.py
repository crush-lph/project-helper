"""
可观测性模块 —— 给 LLM 调用装上"仪表盘"

这个模块做什么？
  记录每次 LLM 调用的详细信息：耗时多少、用了多少 token、调了哪些工具、
  是否出错。所有日志以结构化 JSON 格式输出，方便后续分析和监控。

前端类比：
  就像前端的 Sentry / Datadog RUM SDK —— 自动捕获请求、性能、错误。
  或者像你用 performance.mark() 记录页面加载各阶段耗时。

LangChain 的回调机制：
  LangChain 提供了 BaseCallbackHandler 接口（类似 EventEmitter 的事件监听），
  你只需要实现感兴趣的方法，LangChain 会在合适的时机自动调用它们：
    on_llm_start   → LLM 调用开始前
    on_llm_end     → LLM 调用成功后
    on_llm_error   → LLM 调用失败时
    on_tool_start  → 工具调用开始前
    on_tool_end    → 工具调用成功后
    on_tool_error  → 工具调用失败时
    on_agent_action → Agent 决定调用某个工具时

Python 知识点 —— logging 模块：
  Python 标准库的日志系统，类似 console.log 但更强大：
    - 支持日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
    - 支持格式化输出
    - 支持多个输出目标（控制台、文件、网络）
  我们用 logging.getLogger("project_helper.llm") 创建一个命名的 logger，
  这样可以按模块过滤日志。
"""

from __future__ import annotations

import json       # JSON 序列化，类似 JS 的 JSON.stringify()
import logging    # Python 标准库日志模块
import time       # 高精度计时，类似 JS 的 performance.now()
from typing import Any  # Any 表示"任意类型"，类似 TS 的 any
from uuid import UUID   # UUID 类型，类似 crypto.randomUUID()

from langchain_core.callbacks import BaseCallbackHandler  # LangChain 回调基类
from langchain_core.outputs import LLMResult               # LLM 返回结果的类型


# ---- 日志初始化 ----
# 模块级变量，类似 JS 模块顶层的 let logger = null
_logger: logging.Logger | None = None
# logging.Logger | None 是"联合类型"，表示变量可以是 Logger 或 None
# 类似 TS 的 Logger | null


def get_logger() -> logging.Logger:
    """
    获取日志单例（懒初始化模式）。

    Python 知识点 —— global 关键字：
      global _logger 告诉 Python："我要修改模块级变量 _logger，
      而不是创建一个同名的局部变量。"
      类似 JS 中如果要修改外层作用域的 let 变量，直接赋值即可（不需要关键字）。
      但 Python 的赋值默认创建局部变量，所以需要 global 显式声明。

    Python 知识点 —— Handler 和 Formatter：
      logging.Handler    = 日志输出到哪里（控制台、文件、网络）
      logging.Formatter  = 日志格式化（时间戳、级别、消息内容）
      前端类比：Handler 像 console.log vs console.error，Formatter 像自定义格式。
    """
    global _logger
    if _logger is None:
        # getLogger() 按名称获取 logger，同名返回同一个实例
        _logger = logging.getLogger("project_helper.llm")
        if not _logger.handlers:  # 避免重复添加 handler
            handler = logging.StreamHandler()           # 输出到控制台（stderr）
            handler.setFormatter(logging.Formatter("%(message)s"))  # 只输出消息内容
            _logger.addHandler(handler)
            _logger.setLevel(logging.INFO)  # 只输出 INFO 及以上级别的日志
    return _logger


def _emit(entry: dict[str, Any]) -> None:
    """
    发送一条结构化 JSON 日志。

    Python 知识点 —— json.dumps()：
      把 Python 对象序列化为 JSON 字符串。
      类似 JS 的 JSON.stringify()。
        ensure_ascii=False  →  允许输出中文（默认会把中文转义成 \\uXXXX）
        default=str         →  遇到无法序列化的对象时，用 str() 转换（兜底方案）
    """
    try:
        get_logger().info(json.dumps(entry, ensure_ascii=False, default=str))
    except Exception:
        # 如果 JSON 序列化都失败了（比如有不可预见的类型），输出简化的错误信息
        get_logger().info(json.dumps({"event_type": "log_error", "raw": str(entry)[:500]}))


class LLMCallLogger(BaseCallbackHandler):
    """
    LLM 调用日志记录器。

    继承自 LangChain 的 BaseCallbackHandler，实现各个回调方法。
    前端类比：就像你写一个 class extends EventListener，监听各个事件。

    Python 知识点 —— 类变量 vs 实例变量：
      _MAX_PENDING = 128    →  类变量（所有实例共享，类似 static 属性）
      self._llm_starts = {} →  实例变量（每个实例独立，类似 this.xxx = {}）

    Python 知识点 —— dict（字典）：
      dict[UUID, float] 表示键是 UUID、值是浮点数的字典。
      类似 JS 的 Map<UUID, number>。
      但 Python 的 dict 比 JS 的 Object 更强大：
        - 支持任意类型作为键（不只是字符串）
        - .pop(key, default) 删除并返回值，如果 key 不存在返回 default
    """

    # 类变量：最大待处理条目数，防止内存泄漏
    _MAX_PENDING = 128

    def __init__(self) -> None:
        """
        构造函数。

        Python 知识点 —— super().__init__()：
          调用父类（BaseCallbackHandler）的构造函数。
          类似 JS 的 super()，确保父类的初始化逻辑被正确执行。
          如果不调用，父类的一些内部状态可能不会被正确设置。
        """
        super().__init__()
        self._llm_starts: dict[UUID, float] = {}  # 记录每个 LLM 调用的开始时间
        self._tool_starts: dict[UUID, float] = {}  # 记录每个工具调用的开始时间

    def _evict_stale(self, mapping: dict[UUID, float]) -> None:
        """
        清理过期条目，防止内存泄漏。

        如果某个调用的 on_llm_start 触发了但 on_llm_end 没触发
        （比如进程崩溃），对应的条目会永远留在字典里。
        这个方法在条目数超过阈值时，删除最旧的一半。

        Python 知识点 —— sorted() + key 参数：
          sorted(mapping, key=mapping.get)
          key= 接受一个函数，用于提取排序依据。
          mapping.get 是 dict 的方法，传入 key 返回 value。
          所以这行代码是"按 value（时间戳）从小到大排序"。
        """
        if len(mapping) > self._MAX_PENDING:
            # 取出最旧的一半条目的 key
            oldest = sorted(mapping, key=mapping.get)[: len(mapping) - self._MAX_PENDING // 2]
            for key in oldest:
                del mapping[key]  # del 是 Python 的删除操作符

    def on_llm_start(
        self,
        serialized: dict[str, Any],  # LLM 的序列化信息（模型名等）
        prompts: list[str],           # 发送给 LLM 的 prompt 列表
        *,
        run_id: UUID,                 # 这次调用的唯一 ID
        **kwargs: Any,                # 接收其他可能的参数（LangChain 可能传额外参数）
    ) -> None:
        """
        LLM 调用开始时的回调。

        Python 知识点 —— * 号（强制关键字参数）：
          def foo(a, b, *, c, d):
            a 和 b 是位置参数（positional），可以按位置传
            c 和 d 是强制关键字参数（keyword-only），必须用 c=xxx 的形式传
          这里 * 后面的 run_id 必须用 run_id=xxx 传入，不能按位置。
          前端没有直接对应，但 TypeScript 可以用命名参数模拟。

        Python 知识点 —— **kwargs：
          收集所有未声明的关键字参数到一个字典。
          类似 JS 的 ...rest 参数。
          这样 LangChain 升级后如果传了新参数，我们的代码不会报错。
        """
        self._evict_stale(self._llm_starts)
        self._llm_starts[run_id] = time.monotonic()  # 记录开始时间

        # 从序列化信息中提取模型名
        # .get() 有默认值参数，类似 JS 的 obj?.key ?? fallback
        model = serialized.get("kwargs", {}).get("model_name") or serialized.get("id", [""])[-1]
        prompt_len = sum(len(p) for p in prompts)  # 计算 prompt 总长度

        _emit({
            "event_type": "llm_call",
            "phase": "start",
            "run_id": str(run_id),  # UUID 转字符串，因为 JSON 不支持 UUID 类型
            "model": model,
            "prompt_length": prompt_len,
        })

    def on_llm_end(
        self,
        response: LLMResult,  # LLM 的完整返回结果
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """
        LLM 调用成功时的回调。

        Python 知识点 —— dict.pop(key, default)：
          self._llm_starts.pop(run_id, None)
          删除键为 run_id 的条目并返回其值。
          如果 key 不存在，返回 None（不会报错）。
          类似 JS 的 map.get(key) + map.delete(key) 的组合。

        Python 知识点 —— **token_usage（字典解包）：
          _emit({... "latency_ms": latency_ms, **token_usage})
          **token_usage 把字典的所有键值对展开并合并到外层字典。
          类似 JS 的 {...obj, latency_ms} 展开运算符。
        """
        start = self._llm_starts.pop(run_id, None)
        latency_ms = round((time.monotonic() - start) * 1000) if start else None

        token_usage = self._extract_token_usage(response)

        _emit({
            "event_type": "llm_call",
            "phase": "end",
            "run_id": str(run_id),
            "latency_ms": latency_ms,
            **token_usage,  # 展开字典：把 prompt_tokens, completion_tokens, total_tokens 合并进来
        })

    def on_llm_error(
        self,
        error: BaseException,  # Python 的异常基类（所有异常都继承自它）
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """LLM 调用失败时的回调。"""
        start = self._llm_starts.pop(run_id, None)
        latency_ms = round((time.monotonic() - start) * 1000) if start else None
        _emit({
            "event_type": "llm_call",
            "phase": "error",
            "run_id": str(run_id),
            "latency_ms": latency_ms,
            "error_type": type(error).__name__,  # 获取异常类名，如 "TimeoutException"
            "error_message": str(error)[:500],    # 异常消息，截断到 500 字符
        })

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,  # 工具的输入参数（字符串形式）
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """工具调用开始时的回调。"""
        self._evict_stale(self._tool_starts)
        self._tool_starts[run_id] = time.monotonic()
        _emit({
            "event_type": "tool_call",
            "phase": "start",
            "run_id": str(run_id),
            "tool_name": serialized.get("name", "unknown"),  # 工具名称，如 "search_repo"
            "input_length": len(input_str),                   # len() 获取长度，类似 JS 的 .length
        })

    def on_tool_end(
        self,
        output: str,  # 工具的输出结果
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """工具调用成功时的回调。"""
        start = self._tool_starts.pop(run_id, None)
        latency_ms = round((time.monotonic() - start) * 1000) if start else None
        _emit({
            "event_type": "tool_call",
            "phase": "end",
            "run_id": str(run_id),
            "latency_ms": latency_ms,
            "output_length": len(output),
        })

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """工具调用失败时的回调。"""
        start = self._tool_starts.pop(run_id, None)
        latency_ms = round((time.monotonic() - start) * 1000) if start else None
        _emit({
            "event_type": "tool_call",
            "phase": "error",
            "run_id": str(run_id),
            "latency_ms": latency_ms,
            "error_type": type(error).__name__,
            "error_message": str(error)[:500],
        })

    def on_agent_action(
        self,
        action: Any,  # Agent 决定采取的动作（包含 tool 名称和输入）
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """
        Agent 决定调用某个工具时的回调。

        Python 知识点 —— getattr()：
          getattr(action, "tool", "unknown")
          获取对象的属性，如果属性不存在返回默认值 "unknown"。
          类似 JS 的 action.tool ?? "unknown"
          但 getattr 更安全，因为即使 action 没有 tool 属性也不会报错。
        """
        _emit({
            "event_type": "agent_step",
            "tool_name": getattr(action, "tool", "unknown"),
            "tool_input": str(getattr(action, "tool_input", ""))[:200],  # 截断到 200 字符
        })

    @staticmethod  # 静态方法：不需要 self 参数，类似 JS 的 static method
    def _extract_token_usage(response: LLMResult) -> dict[str, Any]:
        """
        从 LLM 返回结果中提取 token 用量信息。

        不同的 LLM 提供商返回 token 信息的方式不同：
          - OpenAI 兼容接口：在 response.llm_output["token_usage"] 中
          - 新版 LangChain：在 message.usage_metadata 中
        这里两种路径都尝试，确保兼容性。

        Python 知识点 —— or 运算符用于默认值：
          response.llm_output or {}
          如果 llm_output 是 None 或 falsy，就用空字典 {} 代替。
          类似 JS 的 response.llm_output ?? {}
          注意：Python 的 or 在左侧为 falsy 时返回右侧（不只是 null/undefined）。
        """
        usage: dict[str, Any] = {}

        # 路径 1：OpenAI 兼容接口的 token 用量
        llm_output = response.llm_output or {}
        token_usage = llm_output.get("token_usage", {})
        if token_usage:  # 非空字典为 truthy
            usage["prompt_tokens"] = token_usage.get("prompt_tokens", 0)
            usage["completion_tokens"] = token_usage.get("completion_tokens", 0)
            usage["total_tokens"] = token_usage.get("total_tokens", 0)
            return usage

        # 路径 2：从 generation 的 message 元数据中提取
        # response.generations 是嵌套列表：list[list[Generation]]
        for gen_list in response.generations:
            for gen in gen_list:
                msg = getattr(gen, "message", None)  # 安全获取属性
                if msg is None:
                    continue  # 跳过本次循环（类似 JS 的 continue）
                meta = getattr(msg, "usage_metadata", None)
                if meta:
                    usage["prompt_tokens"] = meta.get("input_tokens", 0)
                    usage["completion_tokens"] = meta.get("output_tokens", 0)
                    usage["total_tokens"] = meta.get("total_tokens", 0)
                    return usage

        # 两条路径都没找到，返回零值
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
