import pytest

from app.repository import RepositoryError, normalize_repo_url, project_id_for, project_name_for


ALLOWED_HOSTS = {"github.com", "www.github.com"}


def test_normalize_repo_url_accepts_github_https_and_strips_git_suffix():
    assert (
        normalize_repo_url(" https://github.com/fastapi/fastapi.git ", ALLOWED_HOSTS)
        == "https://github.com/fastapi/fastapi"
    )


def test_normalize_repo_url_accepts_extra_path_segments_but_keeps_owner_repo():
    assert (
        normalize_repo_url("https://www.github.com/openai/openai-python/tree/main", ALLOWED_HOSTS)
        == "https://www.github.com/openai/openai-python"
    )


@pytest.mark.parametrize(
    "repo_url",
    [
        "git@github.com:fastapi/fastapi.git",
        "https://gitlab.com/fastapi/fastapi",
        "https://github.com/",
        "https://github.com/only-owner",
    ],
)
def test_normalize_repo_url_rejects_invalid_or_disallowed_urls(repo_url):
    with pytest.raises(RepositoryError):
        normalize_repo_url(repo_url, ALLOWED_HOSTS)


def test_project_id_is_stable_and_project_name_uses_repo_segment():
    repo_url = "https://github.com/fastapi/fastapi"

    assert project_id_for(repo_url) == project_id_for(repo_url)
    assert len(project_id_for(repo_url)) == 16
    assert project_name_for(repo_url) == "fastapi"
