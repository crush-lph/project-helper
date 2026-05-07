"""Pure check functions for evaluating LLM output quality."""
from __future__ import annotations

import re


def check_sections_present(report: str, required: list[str]) -> list[str]:
    """Return list of required section headers that are missing from the report."""
    missing = []
    for section in required:
        if section not in report:
            missing.append(section)
    return missing


def check_file_refs_valid(report: str, scan_files: list[str]) -> list[str]:
    """Return list of file paths mentioned in report (backtick-wrapped) that don't exist in scan results.

    Only matches backtick-wrapped content containing '.' or '/' to avoid false positives
    on non-path backticks (e.g. `code`). Single-segment names like `cmd` are intentionally
    excluded since they are ambiguous.
    """
    file_set = set(scan_files)
    # Match backtick-wrapped paths that look like file paths (contain / or .)
    candidates = re.findall(r"`([^`]+[./][^`]+)`", report)
    invalid = []
    for ref in candidates:
        ref = ref.strip()
        if not ref or len(ref) > 200:
            continue
        # Skip things that are clearly not file paths
        if ref.startswith("http") or ref.startswith("{") or "=" in ref:
            continue
        if ref not in file_set:
            invalid.append(ref)
    return invalid


def check_no_forbidden_phrases(report: str, forbidden: list[str]) -> list[str]:
    """Return list of forbidden phrases found in the report."""
    found = []
    for phrase in forbidden:
        if phrase.lower() in report.lower():
            found.append(phrase)
    return found


def check_answer_relevance(answer: str, keywords: list[str]) -> float:
    """Return fraction of expected keywords found in the answer (case-insensitive)."""
    if not keywords:
        return 1.0
    answer_lower = answer.lower()
    found = sum(1 for kw in keywords if kw.lower() in answer_lower)
    return found / len(keywords) if keywords else 1.0
