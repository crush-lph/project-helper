from __future__ import annotations

from pathlib import Path

from langchain.tools import tool

from ..core.source_scan import SourceBrowseError, build_tree, number_source_lines, read_source_file
from .schemas import ReadFileInput


def read_repo_file(root_path: str, path: str, max_chars: int = 24_000) -> str:
    """安全读取仓库内文件，并为 Agent 引用返回稳定行号。"""
    try:
        result = read_source_file(Path(root_path), path, max_chars=max_chars)
    except SourceBrowseError as exc:
        return str(exc)

    numbered = number_source_lines(result["content"])
    total_lines = len(result["content"].splitlines()) or 1
    truncated = "是" if result["truncated"] else "否"
    return (
        f"文件: {result['path']}\n"
        f"可引用范围: {result['path']}:1-{total_lines}\n"
        f"内容是否截断: {truncated}\n"
        "请在回答中引用 `文件路径:行号`，例如 "
        f"`{result['path']}:1`。\n\n"
        f"{numbered}"
    )


def build_file_ops_tools(root_path: str):
    """为指定仓库路径构建文件操作工具集。"""

    @tool
    def list_tree() -> str:
        """列出项目目录树（已汇总），用于先定位入口和目录职责，再决定读取哪些文件。"""
        tree = build_tree(Path(root_path), max_entries=260)
        return "目录树已裁剪到 260 条以内；继续用 search_repo 定位关键词，再用 read_file 读取关键文件。\n\n" + tree

    @tool(args_schema=ReadFileInput)
    def read_file(path: str) -> str:
        """按仓库相对路径读取源码文件内容，返回带行号文本，便于回答引用 file:line。"""
        return read_repo_file(root_path, path)

    return [list_tree, read_file]
