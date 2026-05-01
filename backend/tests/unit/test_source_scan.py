from pathlib import Path

from app.source_scan import build_tree, scan_repository, search_code


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_scan_repository_detects_stack_entrypoints_symbols_and_ignores_node_modules(tmp_path):
    write(tmp_path / "README.md", "# Demo\nA useful project.")
    write(tmp_path / "requirements.txt", "fastapi==0.115.6\nlangchain==0.3.14\n")
    write(tmp_path / "app" / "main.py", "class Service:\n    pass\n\ndef health():\n    return {'ok': True}\n")
    write(tmp_path / "node_modules" / "ignored.js", "function shouldNotAppear() {}\n")

    summary = scan_repository(tmp_path)

    assert summary["file_count"] == 3
    assert "FastAPI" in summary["stack"]
    assert "LangChain" in summary["stack"]
    assert "Python" in summary["stack"]
    assert "app/main.py" in summary["entrypoints"]
    assert any("Service" in item and "health" in item for item in summary["symbols"])
    assert "node_modules" not in summary["tree"]


def test_search_code_returns_first_matching_line_per_file(tmp_path):
    write(tmp_path / "app" / "main.py", "def alpha():\n    return 'needle'\n")
    write(tmp_path / "docs.md", "needle appears in docs\n")

    hits = search_code(tmp_path, "needle", limit=5)

    assert "app/main.py:2:" in hits
    assert "docs.md:1:" in hits


def test_build_tree_limits_depth_and_entries(tmp_path):
    write(tmp_path / "a" / "b" / "c" / "d" / "deep.py", "print('hidden')\n")
    write(tmp_path / "root.py", "print('visible')\n")

    tree = build_tree(tmp_path)

    assert "root.py" in tree
    assert "deep.py" not in tree
