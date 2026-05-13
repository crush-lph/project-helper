from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langchain.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

import json

from .config import Settings
from .observability import LLMCallLogger
from .prompts.manager import PromptManager
from .source_scan import read_text, search_code

logger = logging.getLogger(__name__)

_prompts = PromptManager()

_checkpointer = MemorySaver()


def _build_llm_logger() -> LLMCallLogger:
    return LLMCallLogger()


def get_llm(settings: Settings, streaming: bool = False) -> ChatOpenAI | None:
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


# ---- 结构化输出 Schema ----

class ReportSection(BaseModel):
    title: str = Field(description="章节标题")
    content: str = Field(description="章节内容（Markdown）")


class ReportOutput(BaseModel):
    overview: ReportSection = Field(description="项目概述")
    tech_stack: ReportSection = Field(description="技术栈")
    directory_structure: ReportSection = Field(description="目录结构")
    core_modules: ReportSection = Field(description="核心模块")
    data_flow: ReportSection = Field(description="数据流")
    design_patterns: ReportSection = Field(description="设计模式与工程实践")
    reading_path: ReportSection = Field(description="新手阅读路线")
    follow_up_questions: list[str] = Field(description="可继续追问的问题列表")


def build_report_prompt(repo_url: str, summary: dict[str, Any]) -> str:
    return _prompts.render("report_prompt", repo_url=repo_url, summary=summary)


def _parse_report_output(raw: str) -> ReportOutput | None:
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and all(k in data for k in ReportOutput.model_fields):
            return ReportOutput(**data)
        return None
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def generate_llm_report(settings: Settings, repo_url: str, summary: dict[str, Any]) -> str | None:
    llm = get_llm(settings)
    if llm is None:
        return None

    result: ReportOutput | None = None

    try:
        structured_llm = llm.with_structured_output(ReportOutput, method="json_mode")
        result = structured_llm.invoke(build_report_prompt(repo_url, summary))
    except Exception:
        logger.warning("structured output failed, falling back to raw prompt", exc_info=True)

    if result is None:
        try:
            llm_no_tool = get_llm(settings)
            if llm_no_tool:
                prompt = build_report_prompt(repo_url, summary) + (
                    '\n\n请严格按照以下 JSON 格式输出（不要 Markdown 代码块包裹）：\n'
                    + ReportOutput.model_json_schema().__str__()
                )
                raw = llm_no_tool.invoke(prompt).content
                if isinstance(raw, str):
                    result = _parse_report_output(raw)
        except Exception:
            logger.warning("fallback raw prompt also failed", exc_info=True)

    if result is None:
        return None

    sections = [
        result.overview,
        result.tech_stack,
        result.directory_structure,
        result.core_modules,
        result.data_flow,
        result.design_patterns,
        result.reading_path,
    ]
    body = "\n\n".join(f"## {s.title}\n\n{s.content}" for s in sections)
    questions = "\n".join(f"- {q}" for q in result.follow_up_questions)
    return f"{body}\n\n## 可以继续追问\n\n{questions}"


def read_repo_file(root_path: str, path: str, max_chars: int = 24_000) -> str:
    root = Path(root_path).resolve()
    target = (root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return "拒绝读取仓库之外的文件。"
    if not target.exists() or not target.is_file():
        return "文件不存在。"
    return read_text(target, max_chars=max_chars)


# ---- 工具参数 Schema ----

class ReadFileInput(BaseModel):
    path: str = Field(description="仓库相对路径，例如 src/main.py")


class SearchRepoInput(BaseModel):
    query: str = Field(description="搜索关键词，例如 FastAPI、def handle、class User")


# ---- LangGraph Agent ----

def _build_tools(root_path: str):
    """为指定仓库路径构建工具集。"""

    @tool
    def list_tree() -> str:
        """列出项目目录树（已汇总），帮助你了解项目结构。"""
        from .source_scan import build_tree
        return build_tree(Path(root_path), max_entries=260)

    @tool(args_schema=ReadFileInput)
    def read_file(path: str) -> str:
        """按仓库相对路径读取源码文件内容。"""
        return read_repo_file(root_path, path)

    @tool(args_schema=SearchRepoInput)
    def search_repo(query: str) -> str:
        """在全项目中搜索关键词，返回匹配的文件路径和代码行。"""
        return search_code(Path(root_path), query, limit=30)

    return [list_tree, read_file, search_repo]


def create_code_agent(settings: Settings, root_path: str):
    """创建 LangGraph ReAct Agent。

    返回编译后的 agent 图。同一 agent 实例可安全并发使用，
    通过 thread_id (checkpointer) 隔离每轮对话状态。
    """
    llm = get_llm(settings, streaming=True)
    if llm is None:
        return None

    tools = _build_tools(root_path)
    system_prompt = _prompts.get("agent_system_prompt")

    return create_react_agent(
        llm,
        tools,
        prompt=system_prompt,
        checkpointer=_checkpointer,
    )
