from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from .source_scan import iter_source_files, number_source_lines, read_text


def _import_name(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        module = "." * node.level + (node.module or "")
        return [f"{module}.{alias.name}".strip(".") for alias in node.names]
    return []


def _symbol_kind(node: ast.AST, parent: ast.AST | None) -> str:
    if isinstance(node, ast.ClassDef):
        return "class"
    if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
        return "method" if isinstance(parent, ast.ClassDef) else "function"
    return "symbol"


def _collect_python_symbols(path: Path, root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    text = read_text(path, max_chars=350_000)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [], []

    rel = path.relative_to(root).as_posix()
    symbols: list[dict[str, Any]] = []
    imports: list[str] = []

    def visit(node: ast.AST, parent: ast.AST | None = None, prefix: str = "") -> None:
        nonlocal imports
        imports.extend(_import_name(node))
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            name = node.name
            qualified_name = f"{prefix}.{name}" if prefix else name
            symbols.append(
                {
                    "name": name,
                    "kind": _symbol_kind(node, parent),
                    "path": rel,
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "qualified_name": qualified_name,
                }
            )
            child_prefix = qualified_name if isinstance(node, ast.ClassDef) else prefix
        else:
            child_prefix = prefix

        for child in ast.iter_child_nodes(node):
            visit(child, node, child_prefix)

    visit(tree)
    return symbols, imports


def build_symbol_index(root: Path, limit: int = 1200) -> dict[str, Any]:
    """Build a lightweight symbol/import index for currently supported files."""
    root = root.resolve()
    symbols: list[dict[str, Any]] = []
    imports_by_file: dict[str, list[str]] = {}

    for path in iter_source_files(root, limit=limit):
        if path.suffix != ".py":
            continue
        file_symbols, file_imports = _collect_python_symbols(path, root)
        symbols.extend(file_symbols)
        if file_imports:
            imports_by_file[path.relative_to(root).as_posix()] = file_imports

    return {"symbols": symbols, "imports": imports_by_file}


def find_symbols(root: Path, query: str, limit: int = 20) -> list[str]:
    """Find symbols by substring and return compact citable lines."""
    query_lower = query.lower()
    matches: list[str] = []
    for symbol in build_symbol_index(root)["symbols"]:
        haystack = f"{symbol['name']} {symbol['qualified_name']}".lower()
        if query_lower in haystack:
            matches.append(
                f"{symbol['path']}:{symbol['line']}-{symbol['end_line']} "
                f"{symbol['kind']} {symbol['qualified_name']}"
            )
        if len(matches) >= limit:
            break
    return matches


def read_symbol(root: Path, query: str) -> str:
    """Read only the best matching symbol body with line numbers."""
    index = build_symbol_index(root)
    query_lower = query.lower()
    match = next(
        (
            symbol
            for symbol in index["symbols"]
            if query_lower in symbol["name"].lower() or query_lower in symbol["qualified_name"].lower()
        ),
        None,
    )
    if match is None:
        return "没有找到匹配符号。"

    path = root.resolve() / match["path"]
    lines = read_text(path, max_chars=350_000).splitlines()
    body = "\n".join(lines[match["line"] - 1:match["end_line"]])
    return (
        f"符号: {match['kind']} {match['qualified_name']}\n"
        f"位置: {match['path']}:{match['line']}-{match['end_line']}\n"
        "请在回答中引用这个位置范围。\n\n"
        f"{number_source_lines(body, start_line=match['line'])}"
    )
