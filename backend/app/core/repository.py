import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

from git import Repo


class RepositoryError(ValueError):
    pass


def normalize_repo_url(repo_url: str, allowed_hosts: set[str]) -> str:
    value = repo_url.strip()
    if value.endswith(".git"):
        value = value[:-4]
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise RepositoryError("请输入完整的 GitHub HTTPS 仓库地址。")
    if parsed.hostname is None or parsed.hostname.lower() not in allowed_hosts:
        raise RepositoryError("当前演示版只允许分析 GitHub 仓库。")
    path = re.sub(r"/+", "/", parsed.path).strip("/")
    parts = path.split("/")
    if len(parts) < 2 or not all(parts[:2]):
        raise RepositoryError("仓库地址需要包含 owner/repo，例如 https://github.com/fastapi/fastapi。")
    return f"https://{parsed.hostname.lower()}/{parts[0]}/{parts[1]}"


def project_id_for(repo_url: str) -> str:
    return hashlib.sha1(repo_url.encode("utf-8")).hexdigest()[:16]


def project_name_for(repo_url: str) -> str:
    return repo_url.rstrip("/").split("/")[-1]


def clone_or_update(repo_url: str, target: Path) -> None:
    clone_url = repo_url if repo_url.endswith(".git") else f"{repo_url}.git"
    if (target / ".git").exists():
        repo = Repo(target)
        repo.remotes.origin.fetch(depth=1)
        repo.git.reset("--hard", "origin/HEAD")
        return
    if target.exists() and any(target.iterdir()):
        raise RepositoryError(f"目录已存在但不是 Git 仓库：{target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    Repo.clone_from(clone_url, target, depth=1)
