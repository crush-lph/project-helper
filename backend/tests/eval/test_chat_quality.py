"""Eval tests for chat quality (local fallback path)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.analyzer import chat_stream
from app.config import Settings
from .golden_cases import CHAT_CASES


def test_chat_finds_entrypoint(make_repo, eval_settings):
    case = CHAT_CASES[0]
    root = make_repo(case.local_path_setup)
    project = {"local_path": str(root)}

    async def collect():
        return [chunk async for chunk in chat_stream(eval_settings, project, case.question)]

    chunks = asyncio.run(collect())
    full_text = "".join(chunks)

    for keyword in case.expected_keywords:
        assert keyword in full_text, f"Expected keyword '{keyword}' not found in chat response"


def test_chat_finds_function(make_repo, eval_settings):
    case = CHAT_CASES[1]
    root = make_repo(case.local_path_setup)
    project = {"local_path": str(root)}

    async def collect():
        return [chunk async for chunk in chat_stream(eval_settings, project, case.question)]

    chunks = asyncio.run(collect())
    full_text = "".join(chunks)

    for keyword in case.expected_keywords:
        assert keyword in full_text, f"Expected keyword '{keyword}' not found in chat response"
