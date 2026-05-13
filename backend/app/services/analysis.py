from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import anyio

from ..agents.report_agent import generate_llm_report, local_report
from ..config import Settings
from ..database import Database
from ..errors import classify_error
from ..repository import clone_or_update
from ..source_scan import scan_repository


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def make_analysis_locks() -> defaultdict[str, asyncio.Lock]:
    return defaultdict(asyncio.Lock)


async def analyze_project_stream(
    db: Database,
    settings: Settings,
    project: dict[str, Any],
    locks: defaultdict[str, asyncio.Lock] | None = None,
) -> AsyncGenerator[str, None]:
    """4 阶段 SSE 分析管线：clone → scan → report → save。"""
    project_id = project["id"]
    analysis_locks = locks if locks is not None else make_analysis_locks()

    async with analysis_locks[project_id]:
        current_project = db.get_project(project_id) or project

        if current_project["status"] == "ready" and current_project.get("report"):
            yield sse("cached", {"message": "命中缓存，直接返回上次分析结果。", "project_id": project_id})
            yield sse("done", {"project_id": project_id})
            return

        root = Path(current_project["local_path"])
        try:
            db.update_status(project_id, "cloning")
            yield sse("progress", {"step": "clone", "message": "正在克隆或更新仓库..."})
            await anyio.to_thread.run_sync(clone_or_update, current_project["repo_url"], root)

            db.update_status(project_id, "scanning")
            yield sse("progress", {"step": "scan", "message": "正在扫描目录、技术栈和核心文件..."})
            summary = await anyio.to_thread.run_sync(scan_repository, root)

            db.update_status(project_id, "summarizing")
            yield sse("progress", {"step": "summarize", "message": "正在生成通俗版源码报告..."})
            report = await anyio.to_thread.run_sync(generate_llm_report, settings, current_project["repo_url"], summary)

            if report is None:
                report = local_report(current_project["repo_url"], summary)
                summary["llm"] = "DEEPSEEK_API_KEY 未配置，已使用本地静态分析生成报告。"
            else:
                summary["llm"] = f"DeepSeek model: {settings.deepseek_model}"

            db.save_analysis(project_id, report, summary)
            yield sse("done", {"project_id": project_id})

        except Exception as exc:
            error_type, message, _ = classify_error(exc)
            db.update_status(project_id, "failed")
            yield sse("failed", {"message": message, "error_type": error_type})
