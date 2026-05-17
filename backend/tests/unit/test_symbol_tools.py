from pathlib import Path

from app.tools.symbols import build_symbol_tools


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_symbol_tools_find_and_read_python_symbols(tmp_path):
    write(tmp_path / "app" / "main.py", "def target():\n    return 'ok'\n")
    tools = {tool.name: tool for tool in build_symbol_tools(str(tmp_path))}

    matches = tools["find_symbol"].invoke({"query": "target"})
    symbol = tools["read_symbol"].invoke({"query": "target"})

    assert "app/main.py:1-2 function target" in matches
    assert "符号: function target" in symbol
    assert "   1 | def target():" in symbol
