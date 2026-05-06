from pathlib import Path

import pytest

from app.source_scan import SourceBrowseError, build_source_tree, build_tree, read_source_file, scan_repository, search_code


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


def test_build_source_tree_lists_text_files_and_ignores_generated_dirs(tmp_path):
    write(tmp_path / "README.md", "# Demo\n")
    write(tmp_path / "app" / "main.py", "def health():\n    return True\n")
    write(tmp_path / "node_modules" / "ignored.js", "console.log('hidden')\n")
    write(tmp_path / "image.png", "not really an image\n")

    tree = build_source_tree(tmp_path)

    assert tree[0]["path"] == "app"
    assert tree[0]["children"][0]["path"] == "app/main.py"
    assert any(item["path"] == "README.md" for item in tree)
    assert all(item["path"] != "node_modules" for item in tree)
    assert all(item["path"] != "image.png" for item in tree)


def test_build_source_tree_skips_symlinks(tmp_path):
    write(tmp_path / "app" / "main.py", "def health():\n    return True\n")
    write(tmp_path / "linked.py", "print('target')\n")
    (tmp_path / "loop").symlink_to(tmp_path, target_is_directory=True)
    (tmp_path / "app" / "linked.py").symlink_to(tmp_path / "linked.py")

    tree = build_source_tree(tmp_path)
    paths = {item["path"] for item in tree}
    app = next(item for item in tree if item["path"] == "app")
    child_paths = {item["path"] for item in app["children"]}

    assert "loop" not in paths
    assert "app/linked.py" not in child_paths
    assert "app/main.py" in child_paths


def test_read_source_file_rejects_paths_outside_repo(tmp_path):
    root = tmp_path / "repo"
    sibling = tmp_path / "repo-secret"
    write(root / "README.md", "# Safe\n")
    write(sibling / "secret.py", "token = 'hidden'\n")

    with pytest.raises(SourceBrowseError, match="仓库之外"):
        read_source_file(root, "../repo-secret/secret.py")


def test_read_source_file_rejects_symlink_paths(tmp_path):
    write(tmp_path / "safe.py", "print('safe')\n")
    (tmp_path / "linked.py").symlink_to(tmp_path / "safe.py")

    with pytest.raises(SourceBrowseError, match="符号链接"):
        read_source_file(tmp_path, "linked.py")


def test_read_source_file_returns_content_metadata(tmp_path):
    write(tmp_path / "app" / "main.py", "def health():\n    return True\n")

    result = read_source_file(tmp_path, "app/main.py")

    assert result["path"] == "app/main.py"
    assert "def health" in result["content"]
    assert result["size"] > 0
    assert result["truncated"] is False
