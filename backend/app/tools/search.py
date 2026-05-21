from __future__ import annotations

from pathlib import Path

from langchain.tools import tool

from ..core.source_scan import search_code
from .schemas import SearchRepoInput


def build_search_tools(root_path: str):
    """为指定仓库路径构建搜索工具集。"""

    @tool(args_schema=SearchRepoInput)
    def search_repo(query: str) -> str:
        """在全项目中搜索关键词，返回匹配的文件路径和代码行，用于裁剪后续读取范围。"""
        hits = search_code(Path(root_path), query, limit=30)
        return (
            "检索结果格式为 `文件路径:行号: 代码片段`。"
            "回答前请优先 read_file 读取最相关的 1-3 个文件；"
            "如果只基于搜索结果回答，必须说明这是搜索线索而非完整调用链。\n\n"
            f"{hits}"
        )

    return [search_repo]
