from pathlib import Path

from app.symbol_index import build_symbol_index, find_symbols, read_symbol


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_build_symbol_index_extracts_python_symbols_and_imports(tmp_path):
    write(
        tmp_path / "app" / "main.py",
        "import os\n"
        "from fastapi import FastAPI\n\n"
        "class Service:\n"
        "    def health(self):\n"
        "        return True\n\n"
        "def create_app():\n"
        "    return FastAPI()\n",
    )

    index = build_symbol_index(tmp_path)

    assert {
        "name": "Service",
        "kind": "class",
        "path": "app/main.py",
        "line": 4,
        "end_line": 6,
        "qualified_name": "Service",
    } in index["symbols"]
    assert {
        "name": "health",
        "kind": "method",
        "path": "app/main.py",
        "line": 5,
        "end_line": 6,
        "qualified_name": "Service.health",
    } in index["symbols"]
    assert {
        "name": "create_app",
        "kind": "function",
        "path": "app/main.py",
        "line": 8,
        "end_line": 9,
        "qualified_name": "create_app",
    } in index["symbols"]
    assert index["imports"]["app/main.py"] == ["os", "fastapi.FastAPI"]


def test_find_symbols_returns_citable_matches(tmp_path):
    write(tmp_path / "app" / "main.py", "def create_app():\n    return 'ok'\n")

    matches = find_symbols(tmp_path, "create")

    assert matches == [
        "app/main.py:1-2 function create_app",
    ]


def test_read_symbol_returns_only_the_symbol_body_with_line_numbers(tmp_path):
    write(
        tmp_path / "app" / "main.py",
        "def before():\n"
        "    return 'before'\n\n"
        "def target():\n"
        "    value = 1\n"
        "    return value\n\n"
        "def after():\n"
        "    return 'after'\n",
    )

    result = read_symbol(tmp_path, "target")

    assert "符号: function target" in result
    assert "位置: app/main.py:4-6" in result
    assert "   4 | def target():" in result
    assert "   6 |     return value" in result
    assert "before" not in result
    assert "after" not in result
