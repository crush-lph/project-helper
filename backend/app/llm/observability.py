from __future__ import annotations

import json
import logging
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        _logger = logging.getLogger("project_helper.llm")
        if not _logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            _logger.addHandler(handler)
            _logger.setLevel(logging.INFO)
    return _logger


def reset_logger() -> None:
    global _logger
    if _logger:
        for handler in _logger.handlers[:]:
            _logger.removeHandler(handler)
    _logger = None


def _emit(entry: dict[str, Any]) -> None:
    try:
        get_logger().info(json.dumps(entry, ensure_ascii=False, default=str))
    except Exception:
        get_logger().info(json.dumps({"event_type": "log_error", "raw": str(entry)[:500]}))


class LLMMetrics:
    def __init__(self) -> None:
        self.total_llm_calls = 0
        self.total_llm_errors = 0
        self.total_tool_calls = 0
        self.total_tool_errors = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_latency_ms = 0.0

    def snapshot(self) -> dict[str, Any]:
        return {
            "total_llm_calls": self.total_llm_calls,
            "total_llm_errors": self.total_llm_errors,
            "total_tool_calls": self.total_tool_calls,
            "total_tool_errors": self.total_tool_errors,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_latency_ms": round(self.total_latency_ms, 1),
        }


_metrics = LLMMetrics()


def get_metrics() -> LLMMetrics:
    return _metrics


class LLMCallLogger(BaseCallbackHandler):
    _MAX_PENDING = 128

    def __init__(self, metrics: LLMMetrics | None = None) -> None:
        super().__init__()
        self._metrics = metrics or _metrics
        self._llm_starts: dict[UUID, float] = {}
        self._tool_starts: dict[UUID, float] = {}

    @property
    def metrics(self) -> LLMMetrics:
        return self._metrics

    def _evict_stale(self, mapping: dict[UUID, float]) -> None:
        if len(mapping) > self._MAX_PENDING:
            oldest = sorted(mapping, key=lambda run_id: mapping[run_id])[: len(mapping) - self._MAX_PENDING // 2]
            for key in oldest:
                del mapping[key]

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._evict_stale(self._llm_starts)
        self._llm_starts[run_id] = time.monotonic()
        self._metrics.total_llm_calls += 1

        model = serialized.get("kwargs", {}).get("model_name") or serialized.get("id", [""])[-1]
        prompt_len = sum(len(p) for p in prompts)

        _emit({
            "event_type": "llm_call",
            "phase": "start",
            "run_id": str(run_id),
            "model": model,
            "prompt_length": prompt_len,
        })

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        start = self._llm_starts.pop(run_id, None)
        latency_ms = round((time.monotonic() - start) * 1000) if start else None
        if latency_ms:
            self._metrics.total_latency_ms += latency_ms

        token_usage = self._extract_token_usage(response)
        self._metrics.total_prompt_tokens += token_usage.get("prompt_tokens", 0)
        self._metrics.total_completion_tokens += token_usage.get("completion_tokens", 0)

        _emit({
            "event_type": "llm_call",
            "phase": "end",
            "run_id": str(run_id),
            "latency_ms": latency_ms,
            **token_usage,
        })

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        start = self._llm_starts.pop(run_id, None)
        latency_ms = round((time.monotonic() - start) * 1000) if start else None
        self._metrics.total_llm_errors += 1

        _emit({
            "event_type": "llm_call",
            "phase": "error",
            "run_id": str(run_id),
            "latency_ms": latency_ms,
            "error_type": type(error).__name__,
            "error_message": str(error)[:500],
        })

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._evict_stale(self._tool_starts)
        self._tool_starts[run_id] = time.monotonic()
        self._metrics.total_tool_calls += 1
        _emit({
            "event_type": "tool_call",
            "phase": "start",
            "run_id": str(run_id),
            "tool_name": serialized.get("name", "unknown"),
            "input_length": len(input_str),
        })

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
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
        start = self._tool_starts.pop(run_id, None)
        latency_ms = round((time.monotonic() - start) * 1000) if start else None
        self._metrics.total_tool_errors += 1
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
        action: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        _emit({
            "event_type": "agent_step",
            "tool_name": getattr(action, "tool", "unknown"),
            "tool_input": str(getattr(action, "tool_input", ""))[:200],
        })

    @staticmethod
    def _extract_token_usage(response: LLMResult) -> dict[str, Any]:
        usage: dict[str, Any] = {}
        llm_output = response.llm_output or {}
        token_usage = llm_output.get("token_usage", {})
        if token_usage:
            usage["prompt_tokens"] = token_usage.get("prompt_tokens", 0)
            usage["completion_tokens"] = token_usage.get("completion_tokens", 0)
            usage["total_tokens"] = token_usage.get("total_tokens", 0)
            return usage

        for gen_list in response.generations:
            for gen in gen_list:
                msg = getattr(gen, "message", None)
                if msg is None:
                    continue
                meta = getattr(msg, "usage_metadata", None)
                if meta:
                    usage["prompt_tokens"] = meta.get("input_tokens", 0)
                    usage["completion_tokens"] = meta.get("output_tokens", 0)
                    usage["total_tokens"] = meta.get("total_tokens", 0)
                    return usage

        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
