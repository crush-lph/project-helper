"""Eval tests for chat quality (local fallback path)."""
from __future__ import annotations

import asyncio

import pytest

from app.services.chat import chat_stream

from .golden_cases import CHAT_CASES


@pytest.mark.parametrize("case_index", range(len(CHAT_CASES)), ids=[c.question[:30] for c in CHAT_CASES])
def test_chat_finds_expected_keywords(make_repo, eval_settings, case_index):
    case = CHAT_CASES[case_index]
    root = make_repo(case.local_path_setup)
    project = {"local_path": str(root)}

    async def collect():
        return [chunk async for chunk in chat_stream(eval_settings, project, case.question)]

    chunks = asyncio.run(collect())
    full_text = "".join(chunks)

    for keyword in case.expected_keywords:
        assert keyword in full_text, f"Expected keyword '{keyword}' not found in chat response"
