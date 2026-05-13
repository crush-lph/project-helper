from app.tools.file_ops import read_repo_file


def test_read_repo_file_rejects_sibling_directory_with_same_prefix(tmp_path):
    root = tmp_path / "repo"
    sibling = tmp_path / "repo-secret"
    root.mkdir()
    sibling.mkdir()
    (sibling / "secret.txt").write_text("do not read", encoding="utf-8")

    result = read_repo_file(str(root), "../repo-secret/secret.txt")

    assert result == "拒绝读取仓库之外的文件。"


def test_read_repo_file_allows_files_inside_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("# Safe\n", encoding="utf-8")

    assert read_repo_file(str(root), "README.md") == "# Safe\n"
