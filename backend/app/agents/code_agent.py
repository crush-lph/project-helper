from __future__ import annotations

from typing import Any, AsyncGenerator

from langgraph.prebuilt import create_react_agent

from ..config import Settings
from ..llm import get_llm
from ..memory import get_checkpointer
from ..prompts.manager import PromptManager
from ..tools import build_file_ops_tools, build_search_tools

_prompts = PromptManager()


def create_code_agent(settings: Settings, root_path: str):
    """创建 LangGraph ReAct Agent。

    返回编译后的 agent 图。同一实例可安全并发使用，
    通过 thread_id (checkpointer) 隔离每轮对话状态。
    """
    llm = get_llm(settings, streaming=True)
    if llm is None:
        return None

    tools = build_file_ops_tools(root_path) + build_search_tools(root_path)
    system_prompt = _prompts.get("agent_system_prompt")

    return create_react_agent(
        llm,
        tools,
        prompt=system_prompt,
        checkpointer=get_checkpointer(),
    )


async def stream_agent_events(agent, question: str, thread_id: str) -> AsyncGenerator[dict[str, str], None]:
    """LangGraph agent 原生异步流式输出。

    使用 astream_events 监听三类事件：
    - on_chat_model_stream → 逐 Token 推送
    - on_tool_start → 推送 Tool 名称和输入
    - on_tool_end → 推送 Tool 输出
    """
    input_msg = {"messages": [("human", question)]}
    config = {"configurable": {"thread_id": thread_id}}

    async for event in agent.astream_events(input_msg, config=config, version="v2"):
        kind = event.get("event")

        if kind == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if chunk and chunk.content:
                yield {"type": "token", "text": chunk.content}

        elif kind == "on_tool_start":
            yield {
                "type": "tool_start",
                "tool": event.get("name", ""),
                "input": str(event.get("input", ""))[:200],
            }

        elif kind == "on_tool_end":
            output = str(event.get("data", {}).get("output", ""))[:300]
            if output:
                yield {"type": "tool_end", "output": output}
