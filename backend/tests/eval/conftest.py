"""Shared fixtures for eval tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings


@pytest.fixture()
def eval_settings(tmp_path: Path) -> Settings:
    return Settings(deepseek_api_key="", data_dir=tmp_path / "data")


@pytest.fixture()
def make_repo(tmp_path: Path):
    """Factory fixture that creates a temporary repo with given file contents."""
    def _make(files: dict[str, str]) -> Path:
        root = tmp_path / "repo"
        root.mkdir(exist_ok=True)
        for rel_path, content in files.items():
            file_path = root / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
        return root
    return _make
