from __future__ import annotations

from pathlib import Path

from langchain.tools import tool

from ..source_scan import build_tree, read_text
from .schemas import ReadFileInput


def read_repo_file(root_path: str, path: str, max_chars: int = 24_000) -> str:
    """安全读取仓库内文件，含路径穿越防护。"""
    root = Path(root_path).resolve()
    target = (root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return "拒绝读取仓库之外的文件。"
    if not target.exists() or not target.is_file():
        return "文件不存在。"
    return read_text(target, max_chars=max_chars)


def build_file_ops_tools(root_path: str):
    """为指定仓库路径构建文件操作工具集。"""

    @tool
    def list_tree() -> str:
        """列出项目目录树（已汇总），帮助你了解项目结构。"""
        return build_tree(Path(root_path), max_entries=260)

    @tool(args_schema=ReadFileInput)
    def read_file(path: str) -> str:
        """按仓库相对路径读取源码文件内容。"""
        return read_repo_file(root_path, path)

    return [list_tree, read_file]
