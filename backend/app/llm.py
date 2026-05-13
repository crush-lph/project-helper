from __future__ import annotations

from langchain_openai import ChatOpenAI

from .config import Settings
from .observability import LLMCallLogger


def _build_llm_logger() -> LLMCallLogger:
    return LLMCallLogger()


def get_llm(settings: Settings, streaming: bool = False) -> ChatOpenAI | None:
    """创建 LLM 客户端实例。返回 None 表示未配置 API Key。"""
    if not settings.deepseek_api_key:
        return None
    return ChatOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        temperature=0.2,
        streaming=streaming,
        max_retries=settings.llm_max_retries,
        request_timeout=settings.llm_timeout,
        callbacks=[_build_llm_logger()],
    )
