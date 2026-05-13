from __future__ import annotations

from pathlib import Path

from langchain.tools import tool

from ..source_scan import search_code
from .schemas import SearchRepoInput


def build_search_tools(root_path: str):
    """为指定仓库路径构建搜索工具集。"""

    @tool(args_schema=SearchRepoInput)
    def search_repo(query: str) -> str:
        """在全项目中搜索关键词，返回匹配的文件路径和代码行。"""
        return search_code(Path(root_path), query, limit=30)

    return [search_repo]
