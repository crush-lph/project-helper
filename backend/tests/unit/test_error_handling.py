from __future__ import annotations

import httpx

from app.errors import classify_error


def test_classify_timeout_as_transient():
    exc = httpx.TimeoutException("connection timed out")
    error_type, message, original = classify_error(exc)
    assert error_type == "transient"
    assert "超时" in message
    assert original is exc


def test_classify_connect_error_as_transient():
    exc = httpx.ConnectError("connection refused")
    error_type, message, _ = classify_error(exc)
    assert error_type == "transient"


def test_classify_429_as_rate_limit():
    resp = httpx.Response(429)
    exc = httpx.HTTPStatusError("rate limited", request=httpx.Request("GET", "http://test"), response=resp)
    error_type, message, _ = classify_error(exc)
    assert error_type == "rate_limit"
    assert "频率" in message


def test_classify_500_as_transient():
    resp = httpx.Response(500)
    exc = httpx.HTTPStatusError("server error", request=httpx.Request("GET", "http://test"), response=resp)
    error_type, message, _ = classify_error(exc)
    assert error_type == "transient"


def test_classify_os_error_as_transient():
    exc = OSError("disk full")
    error_type, message, _ = classify_error(exc)
    assert error_type == "transient"
    assert "disk full" in message


def test_classify_generic_exception_as_permanent():
    exc = ValueError("something unexpected")
    error_type, message, _ = classify_error(exc)
    assert error_type == "permanent"
    assert "something unexpected" in message


def test_classify_git_connect_error_as_transient():
    import git
    exc = git.exc.GitCommandError(
        ["git", "clone", "-v", "--depth=1", "--", "https://github.com/Fission-AI/OpenSpec.git"],
        128,
        stderr="Cloning into '...'...\nfatal: unable to access '...': Failed to connect to github.com port 443: Couldn't connect to server",
    )
    error_type, message, _ = classify_error(exc)
    assert error_type == "transient"
    assert "GitHub" in message


def test_classify_git_auth_error_as_permanent():
    import git
    exc = git.exc.GitCommandError(
        ["git", "clone", "https://github.com/foo/private.git"],
        128,
        stderr="fatal: Authentication failed for 'https://github.com/foo/private.git/'",
    )
    error_type, message, _ = classify_error(exc)
    assert error_type == "permanent"
    assert "认证" in message


def test_classify_git_not_found_as_permanent():
    import git
    exc = git.exc.GitCommandError(
        ["git", "clone", "https://github.com/foo/nonexistent.git"],
        128,
        stderr="fatal: repository 'https://github.com/foo/nonexistent.git/' not found",
    )
    error_type, message, _ = classify_error(exc)
    assert error_type == "permanent"
    assert "不存在" in message
