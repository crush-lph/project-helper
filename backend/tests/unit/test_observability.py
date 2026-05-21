"""Tests for the observability module."""
from __future__ import annotations

import json
import logging
from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.llm.observability import LLMCallLogger, get_logger


def test_extract_token_usage_from_llm_output():
    response = LLMResult(
        generations=[[ChatGeneration(message=AIMessage(content="hi"))]],
        llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}},
    )
    usage = LLMCallLogger._extract_token_usage(response)
    assert usage["prompt_tokens"] == 10
    assert usage["completion_tokens"] == 20
    assert usage["total_tokens"] == 30


def test_extract_token_usage_from_message_metadata():
    msg = AIMessage(content="hi")
    msg.usage_metadata = {"input_tokens": 5, "output_tokens": 15, "total_tokens": 20}
    response = LLMResult(
        generations=[[ChatGeneration(message=msg)]],
        llm_output={},
    )
    usage = LLMCallLogger._extract_token_usage(response)
    assert usage["prompt_tokens"] == 5
    assert usage["completion_tokens"] == 15
    assert usage["total_tokens"] == 20


def test_extract_token_usage_returns_zeros_when_missing():
    response = LLMResult(
        generations=[[ChatGeneration(message=AIMessage(content="hi"))]],
        llm_output={},
    )
    usage = LLMCallLogger._extract_token_usage(response)
    assert usage["prompt_tokens"] == 0
    assert usage["completion_tokens"] == 0
    assert usage["total_tokens"] == 0


def test_on_llm_end_logs_json(caplog):
    logger = LLMCallLogger()
    run_id = uuid4()
    logger._llm_starts[run_id] = 0.0

    response = LLMResult(
        generations=[[ChatGeneration(message=AIMessage(content="hi"))]],
        llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}},
    )

    with caplog.at_level(logging.INFO, logger="project_helper.llm"):
        logger.on_llm_end(response, run_id=run_id)

    assert len(caplog.records) >= 1
    entry = json.loads(caplog.records[-1].message)
    assert entry["event_type"] == "llm_call"
    assert entry["phase"] == "end"
    assert entry["prompt_tokens"] == 10
    assert entry["completion_tokens"] == 20


def test_on_llm_error_logs_error(caplog):
    logger = LLMCallLogger()
    run_id = uuid4()
    logger._llm_starts[run_id] = 0.0

    with caplog.at_level(logging.INFO, logger="project_helper.llm"):
        logger.on_llm_error(Exception("test error"), run_id=run_id)

    assert len(caplog.records) >= 1
    entry = json.loads(caplog.records[-1].message)
    assert entry["event_type"] == "llm_call"
    assert entry["phase"] == "error"
    assert entry["error_type"] == "Exception"
    assert "test error" in entry["error_message"]


def test_on_tool_start_and_end(caplog):
    logger = LLMCallLogger()
    run_id = uuid4()

    with caplog.at_level(logging.INFO, logger="project_helper.llm"):
        logger.on_tool_start({"name": "search_repo"}, "query text", run_id=run_id)
        logger.on_tool_end("result output", run_id=run_id)

    messages = [json.loads(r.message) for r in caplog.records]
    start = next(m for m in messages if m.get("phase") == "start")
    end = next(m for m in messages if m.get("phase") == "end")

    assert start["tool_name"] == "search_repo"
    assert start["input_length"] == 10
    assert end["output_length"] == 13


def test_on_agent_action_logs_tool_name(caplog):
    logger = LLMCallLogger()

    class FakeAction:
        tool = "read_file"
        tool_input = {"path": "main.py"}

    with caplog.at_level(logging.INFO, logger="project_helper.llm"):
        logger.on_agent_action(FakeAction(), run_id=uuid4())

    entry = json.loads(caplog.records[-1].message)
    assert entry["event_type"] == "agent_step"
    assert entry["tool_name"] == "read_file"


def test_get_logger_returns_singleton():
    logger1 = get_logger()
    logger2 = get_logger()
    assert logger1 is logger2
    assert logger1.name == "project_helper.llm"
