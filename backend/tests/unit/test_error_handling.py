"""Tests for error classification and handling."""
from __future__ import annotations

from app.analyzer import classify_error


def test_classify_timeout_as_transient():
    try:
        import httpx

        exc = httpx.TimeoutException("connection timed out")
        error_type, message = classify_error(exc)
        assert error_type == "transient"
        assert "超时" in message
    except ImportError:
        pass  # httpx not available


def test_classify_connect_error_as_transient():
    try:
        import httpx

        exc = httpx.ConnectError("connection refused")
        error_type, message = classify_error(exc)
        assert error_type == "transient"
    except ImportError:
        pass


def test_classify_429_as_rate_limit():
    try:
        import httpx

        resp = httpx.Response(429)
        exc = httpx.HTTPStatusError("rate limited", request=httpx.Request("GET", "http://test"), response=resp)
        error_type, message = classify_error(exc)
        assert error_type == "rate_limit"
        assert "频率" in message
    except ImportError:
        pass


def test_classify_500_as_transient():
    try:
        import httpx

        resp = httpx.Response(500)
        exc = httpx.HTTPStatusError("server error", request=httpx.Request("GET", "http://test"), response=resp)
        error_type, message = classify_error(exc)
        assert error_type == "transient"
    except ImportError:
        pass


def test_classify_os_error_as_transient():
    exc = OSError("disk full")
    error_type, message = classify_error(exc)
    assert error_type == "transient"
    assert "disk full" in message


def test_classify_generic_exception_as_permanent():
    exc = ValueError("something unexpected")
    error_type, message = classify_error(exc)
    assert error_type == "permanent"
    assert "something unexpected" in message
