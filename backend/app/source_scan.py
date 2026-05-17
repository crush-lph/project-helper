from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

IGNORE_DIRS = {
    ".git", ".idea", ".vscode", "__pycache__", "node_modules", "dist", "build",
    ".next", ".venv", "venv", "target", "coverage", ".pytest_cache",
}
TEXT_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".vue", ".go", ".rs", ".java", ".kt",
    ".php", ".rb", ".cs", ".c", ".cpp", ".h", ".hpp", ".swift", ".scala",
    ".md", ".rst", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".env",
    ".html", ".css", ".scss", ".sql", ".sh", ".Dockerfile",
}
CONFIG_FILES = {
    "package.json", "pyproject.toml", "requirements.txt", "poetry.lock", "Pipfile",
    "go.mod", "Cargo.toml", "pom.xml", "build.gradle", "docker-compose.yml",
    "Dockerfile", "Makefile", "README", "LICENSE", "NOTICE",
    "vite.config.ts", "vite.config.js", "next.config.js",
}


class SourceBrowseError(ValueError):
    pass


def is_text_file(path: Path) -> bool:
    return path.name in CONFIG_FILES or path.suffix in TEXT_SUFFIXES


def is_within_root(path: Path, root: Path) -> bool:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def safe_source_path(root: Path, relative_path: str) -> Path:
    value = (relative_path or "").strip().lstrip("/")
    if not value or value == ".":
        raise SourceBrowseError("请选择要查看的源码文件。")
    candidate = root / value
    if has_symlink_component(root, candidate):
        raise SourceBrowseError("拒绝读取符号链接文件。")
    target = candidate.resolve()
    if not is_within_root(target, root):
        raise SourceBrowseError("拒绝读取仓库之外的文件。")
    return target


def has_symlink_component(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def iter_source_files(root: Path, limit: int = 900) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in IGNORE_DIRS and not name.startswith(".cache")]
        for filename in filenames:
            path = Path(dirpath) / filename
            if is_text_file(path) and path.stat().st_size <= 350_000:
                files.append(path)
            if len(files) >= limit:
                return files
    return files


def read_text(path: Path, max_chars: int = 16_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except OSError as exc:
        return f"读取失败：{exc}"


def number_source_lines(content: str, start_line: int = 1) -> str:
    """Render source text with stable 1-based line numbers for citations."""
    lines = content.splitlines()
    if not lines:
        return f"{start_line:>4} | "
    return "\n".join(f"{number:>4} | {line}" for number, line in enumerate(lines, start=start_line))


def build_source_tree(root: Path, max_entries: int = 900) -> list[dict[str, Any]]:
    root = root.resolve()
    count = 0

    def walk_dir(directory: Path) -> list[dict[str, Any]]:
        nonlocal count
        if count >= max_entries:
            return []
        entries: list[dict[str, Any]] = []
        try:
            children = sorted(directory.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))
        except OSError:
            return entries

        for child in children:
            if count >= max_entries:
                break
            if child.is_symlink():
                continue
            if not is_within_root(child, root):
                continue
            if child.is_dir():
                if child.name in IGNORE_DIRS or child.name.startswith(".cache"):
                    continue
                nested = walk_dir(child)
                if nested:
                    count += 1
                    rel = child.relative_to(root).as_posix()
                    entries.append({"type": "directory", "name": child.name, "path": rel, "children": nested})
                continue
            if not child.is_file() or not is_text_file(child):
                continue
            try:
                size = child.stat().st_size
            except OSError:
                continue
            if size > 350_000:
                continue
            count += 1
            rel = child.relative_to(root).as_posix()
            entries.append({"type": "file", "name": child.name, "path": rel, "size": size})
        return entries

    return walk_dir(root)


def read_source_file(root: Path, relative_path: str, max_chars: int = 120_000) -> dict[str, Any]:
    target = safe_source_path(root, relative_path)
    if not target.exists() or not target.is_file():
        raise SourceBrowseError("文件不存在。")
    if not is_text_file(target):
        raise SourceBrowseError("只能查看文本源码文件。")
    try:
        size = target.stat().st_size
    except OSError as exc:
        raise SourceBrowseError(f"读取失败：{exc}") from exc
    if size > 350_000:
        raise SourceBrowseError("文件过大，暂不支持直接预览。")
    return {
        "path": target.relative_to(root.resolve()).as_posix(),
        "content": read_text(target, max_chars=max_chars),
        "size": size,
        "truncated": size > max_chars,
    }


def build_tree(root: Path, max_entries: int = 220) -> str:
    lines: list[str] = []
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in sorted(dirnames) if name not in IGNORE_DIRS]
        rel = Path(dirpath).relative_to(root)
        depth = 0 if str(rel) == "." else len(rel.parts)
        if depth > 3:
            dirnames[:] = []
            continue
        indent = "  " * depth
        if str(rel) != ".":
            lines.append(f"{indent}{rel.name}/")
            count += 1
        for filename in sorted(filenames)[:18]:
            if count >= max_entries:
                lines.append("  ...")
                return "\n".join(lines)
            path = Path(dirpath) / filename
            if is_text_file(path):
                lines.append(f"{indent}  {filename}")
                count += 1
    return "\n".join(lines)


def detect_stack(files: list[Path], root: Path) -> list[str]:
    names = {path.name for path in files}
    suffixes = Counter(path.suffix for path in files)
    stack: list[str] = []
    if "package.json" in names:
        package = read_text(root / "package.json", 8000)
        for key in ["vue", "react", "next", "vite", "express", "nestjs", "tailwindcss"]:
            if f'"{key}"' in package:
                stack.append(key)
        stack.append("Node.js")
    if "pyproject.toml" in names or "requirements.txt" in names:
        req_text = "\n".join(read_text(root / name, 8000) for name in ["pyproject.toml", "requirements.txt"] if (root / name).exists())
        if "fastapi" in req_text.lower():
            stack.append("FastAPI")
        if "django" in req_text.lower():
            stack.append("Django")
        if "langchain" in req_text.lower():
            stack.append("LangChain")
        stack.append("Python")
    if "go.mod" in names:
        stack.append("Go")
    if "Cargo.toml" in names:
        stack.append("Rust")
    if "pom.xml" in names or "build.gradle" in names:
        stack.append("Java/JVM")
    if suffixes[".vue"]:
        stack.append("Vue")
    if suffixes[".tsx"] or suffixes[".jsx"]:
        stack.append("TypeScript/React")
    return sorted(set(stack), key=stack.index)


def find_entrypoints(files: list[Path], root: Path) -> list[str]:
    patterns = [
        "main.py", "app.py", "server.py", "index.js", "index.ts", "main.ts", "main.js",
        "App.vue", "main.go", "src/main.rs", "cmd",
    ]
    found: list[str] = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        if path.name in patterns or rel in patterns or "/main." in rel:
            found.append(rel)
    return found[:20]


def extract_symbols(path: Path, root: Path) -> list[str]:
    text = read_text(path, 20_000)
    symbols: list[str] = []
    for pattern in [
        r"^\s*(?:async\s+)?def\s+([A-Za-z_][\w]*)",
        r"^\s*class\s+([A-Za-z_][\w]*)",
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][\w]*)",
        r"^\s*(?:const|let)\s+([A-Za-z_][\w]*)\s*=",
    ]:
        symbols.extend(re.findall(pattern, text, flags=re.MULTILINE))
    rel = path.relative_to(root).as_posix()
    return [f"{rel}: {', '.join(symbols[:12])}"] if symbols else []


def scan_repository(root: Path) -> dict[str, Any]:
    files = iter_source_files(root)
    suffix_counts = Counter(path.suffix or path.name for path in files)
    top_dirs = Counter((path.relative_to(root).parts[0] if path.relative_to(root).parts else ".") for path in files)
    core_files = sorted(files, key=lambda p: (p.parts.count("src") == 0, len(p.parts), p.name))[:45]
    symbols: list[str] = []
    for path in core_files[:25]:
        symbols.extend(extract_symbols(path, root))
    readme = ""
    for name in ["README.md", "readme.md", "README.rst", "README"]:
        if (root / name).exists():
            readme = read_text(root / name, 20_000)
            break
    return {
        "tree": build_tree(root),
        "file_count": len(files),
        "extensions": dict(suffix_counts.most_common(12)),
        "top_dirs": dict(top_dirs.most_common(12)),
        "stack": detect_stack(files, root),
        "entrypoints": find_entrypoints(files, root),
        "symbols": symbols[:60],
        "readme": readme,
        "core_files": [path.relative_to(root).as_posix() for path in core_files],
    }


def search_code(root: Path, query: str, limit: int = 20) -> str:
    query_lower = query.lower()
    hits: list[str] = []
    for path in iter_source_files(root, limit=1200):
        rel = path.relative_to(root).as_posix()
        if query_lower in rel.lower():
            hits.append(f"{rel}:1: 文件路径匹配")
            if len(hits) >= limit:
                break
            continue
        text = read_text(path, 80_000)
        for number, line in enumerate(text.splitlines(), start=1):
            if query_lower in line.lower():
                hits.append(f"{rel}:{number}: {line.strip()[:220]}")
                break
        if len(hits) >= limit:
            break
    return "\n".join(hits) if hits else "没有找到匹配代码。"
