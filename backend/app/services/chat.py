from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import anyio

from ..agents.code_agent import create_code_agent, stream_agent_events
from ..config import Settings
from ..errors import classify_error
from ..source_scan import search_code
from ..tools.file_ops import read_repo_file
from ..utils.sse import sse


def _build_file_context(root: Path, file_paths: list[str]) -> str:
    """读取用户引用的文件，组装成上下文文本。"""
    if not file_paths:
        return ""
    blocks = []
    for path in file_paths[:10]:
        content = read_repo_file(str(root), path)
        if content and not content.startswith("拒绝") and not content.startswith("文件不存在"):
            blocks.append(f"### `{path}`\n\n```\n{content}```")
    if not blocks:
        return ""
    return "\n\n".join(blocks)


async def chat_stream(
    settings: Settings,
    project: dict[str, Any],
    question: str,
    file_paths: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    """聊天 SSE 流：Agent 问答 or 本地搜索 fallback。"""
    root = Path(project["local_path"])
    agent = create_code_agent(settings, str(root))

    file_context = _build_file_context(root, file_paths or [])

    if agent is None:
        yield sse("token", {"text": "当前未配置 DEEPSEEK_API_KEY，我先用本地搜索给你一个可验证答案。\n\n"})
        keywords = [part for part in question.replace("，", " ").replace("？", " ").split() if len(part) >= 2]
        query = keywords[0] if keywords else question[:20]
        hits = await anyio.to_thread.run_sync(lambda: search_code(root, query, limit=12))
        context_note = f"\n\n## 引用文件上下文\n\n{file_context}\n\n" if file_context else ""
        answer = f"{context_note}我搜索了关键词 `{query}`，找到这些线索：\n\n```text\n{hits}\n```\n\n建议你继续追问一个更具体的问题，例如「解释第一个文件的作用」或「沿着这个函数追调用链」。"
        for chunk in answer.splitlines(keepends=True):
            yield sse("token", {"text": chunk})
        yield sse("done", {})
        return

    try:
        project_id = project.get("id", "default")
        agent_input = question
        if file_context:
            agent_input = (
                f"以下是用户引用的源码文件，请基于这些内容回答问题：\n\n{file_context}\n\n"
                f"---\n\n用户问题：{question}"
            )

        async for event in stream_agent_events(agent, agent_input, thread_id=project_id):
            if event["type"] == "token":
                yield sse("token", {"text": event["text"]})
            elif event["type"] == "tool_start":
                yield sse("agent", {"type": "action", "data": {"tool": event["tool"], "input": event["input"]}})
            elif event["type"] == "tool_end":
                yield sse("agent", {"type": "observation", "data": {"output": event["output"]}})

        yield sse("done", {})
    except Exception as exc:
        _, message, original = classify_error(exc)
        yield sse("failed", {"message": message, "error_type": type(original).__name__})
