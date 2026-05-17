"""Tests for the prompt management module."""
from __future__ import annotations

from app.prompts.manager import PromptManager


def test_get_report_prompt():
    pm = PromptManager()
    content = pm.get("report_prompt")
    assert "project-helper" in content
    assert "{repo_url}" in content
    assert "{summary}" in content


def test_get_agent_system_prompt():
    pm = PromptManager()
    content = pm.get("agent_system_prompt")
    assert "Agent" in content
    assert "search_repo" in content
    assert "文件路径:行号" in content
    assert "源码依据" in content


def test_render_substitutes_variables():
    pm = PromptManager()
    result = pm.render("report_prompt", repo_url="https://github.com/test/test", summary="{}")
    assert "https://github.com/test/test" in result
    assert "{repo_url}" not in result


def test_list_prompts():
    pm = PromptManager()
    names = pm.list_prompts()
    assert "report_prompt" in names
    assert "agent_system_prompt" in names


def test_build_report_prompt_regression():
    from app.agents.report_agent import build_report_prompt

    result = build_report_prompt("https://github.com/owner/repo", {"stack": ["Python"]})
    assert "project-helper" in result
    assert "https://github.com/owner/repo" in result
    assert "Python" in str(result)
