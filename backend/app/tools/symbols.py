from __future__ import annotations

from pathlib import Path

from langchain.tools import tool

from ..symbol_index import find_symbols, read_symbol as read_index_symbol
from .schemas import SymbolQueryInput


def build_symbol_tools(root_path: str):
    """Build symbol-level tools backed by the lightweight AST index."""

    @tool(args_schema=SymbolQueryInput)
    def find_symbol(query: str) -> str:
        """按符号名查找 Python 函数、类、方法，返回可引用的 path:line 范围。"""
        matches = find_symbols(Path(root_path), query, limit=20)
        if not matches:
            return "没有找到匹配符号。可以退回 search_repo 做文本检索。"
        return (
            "符号索引当前优先支持 Python AST。结果格式为 `文件路径:起止行 类型 符号名`；"
            "下一步通常用 read_symbol 读取最相关符号体。\n\n"
            + "\n".join(matches)
        )

    @tool(args_schema=SymbolQueryInput)
    def read_symbol(query: str) -> str:
        """读取匹配符号的最小源码范围，返回带行号的函数/类/方法源码。"""
        return read_symbol_body(root_path, query)

    return [find_symbol, read_symbol]


def read_symbol_body(root_path: str, query: str) -> str:
    return read_index_symbol(Path(root_path), query)
