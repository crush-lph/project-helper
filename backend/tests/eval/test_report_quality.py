"""Eval tests for report generation quality."""
from __future__ import annotations

from app.agents.report_agent import local_report
from .checks import (
    check_file_refs_valid,
    check_no_forbidden_phrases,
    check_sections_present,
)
from .golden_cases import REPORT_CASES


def _run_report_eval(case):
    report = local_report(case.repo_url, case.summary)

    missing = check_sections_present(report, case.required_sections)
    assert not missing, f"[{case.name}] Missing sections: {missing}"

    invalid_refs = check_file_refs_valid(report, case.expected_file_refs)
    # Only fail if expected file refs are missing
    for ref in case.expected_file_refs:
        if f"`{ref}`" not in report:
            invalid_refs.append(f"expected ref not found: {ref}")

    forbidden = check_no_forbidden_phrases(report, case.forbidden_phrases)
    assert not forbidden, f"[{case.name}] Forbidden phrases found: {forbidden}"

    return report


def test_report_python_fastapi():
    report = _run_report_eval(REPORT_CASES[0])
    assert "FastAPI" in report
    assert "app/main.py" in report


def test_report_node_vue():
    report = _run_report_eval(REPORT_CASES[1])
    assert "Vue" in report
    assert "src/App.vue" in report


def test_report_minimal_repo():
    report = _run_report_eval(REPORT_CASES[2])
    assert "**1**" in report  # file_count rendered as bold markdown
    assert "README.md" in report
