from __future__ import annotations

import git
import httpx


def classify_error(exc: Exception) -> tuple[str, str, Exception]:
    """将异常分类为 transient / rate_limit / permanent，返回 (类型, 用户提示, 原始异常)。"""
    if isinstance(exc, httpx.TimeoutException | httpx.ConnectError):
        return "transient", "网络连接超时，请稍后重试。", exc
    
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code == 429:
            return "rate_limit", "API 请求频率超限，请稍后重试。", exc
        if exc.response.status_code >= 500:
            return "transient", "API 服务暂时不可用，请稍后重试。", exc
        return "permanent", f"API 请求失败：{exc.response.status_code}", exc
    
    if isinstance(exc, OSError | PermissionError):
        return "transient", f"文件系统错误：{exc}", exc
    
    if isinstance(exc, git.exc.GitCommandError):
        stderr = exc.stderr or ""
        if "Couldn't connect" in stderr or "Failed to connect" in stderr:
            return "transient", "无法连接到 GitHub，请检查网络连接或稍后重试。", exc
        if "Authentication failed" in stderr or "Access denied" in stderr:
            return "permanent", "GitHub 认证失败：该仓库可能不存在或没有访问权限。", exc
        if "Repository not found" in stderr or "not found" in stderr:
            return "permanent", "仓库不存在，请检查链接是否正确。", exc
        return "transient", f"Git 操作失败：{stderr[:200]}", exc
    return "permanent", f"未知错误：{exc}", exc
