from __future__ import annotations

from typing import Any

from langchain.tools import tool
from langchain_openai import ChatOpenAI

from .config import Settings
from .source_scan import read_text, search_code


def get_llm(settings: Settings, streaming: bool = False) -> ChatOpenAI | None:
    if not settings.deepseek_api_key:
        return None
    return ChatOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        temperature=0.2,
        streaming=streaming,
    )


def build_report_prompt(repo_url: str, summary: dict[str, Any]) -> str:
    return f"""
你是 project-helper，一个把源码讲到新手也能懂的项目学习助手。
请基于下面的真实源码扫描结果，输出一份中文 Markdown 完整分析报告。

要求：
- 语言通俗，但不要牺牲准确性。
- 必须包含：项目概述、技术栈、目录结构、核心模块、数据流、设计模式/工程实践、从哪里开始读、适合新手的阅读路线、可继续追问的问题。
- 对不确定的地方明确说“从当前扫描结果推断”。
- 代码路径必须来自扫描结果，不要编造文件。

仓库：{repo_url}
扫描结果：
{summary}
"""


def generate_llm_report(settings: Settings, repo_url: str, summary: dict[str, Any]) -> str | None:
    llm = get_llm(settings)
    if llm is None:
        return None
    response = llm.invoke(build_report_prompt(repo_url, summary))
    return str(response.content)


def create_code_agent(settings: Settings, root_path: str):
    llm = get_llm(settings, streaming=True)
    if llm is None:
        return None
    try:
        from langchain.agents import AgentExecutor, create_tool_calling_agent
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    except ImportError:
        return None

    @tool
    def list_tree() -> str:
        """List the repository directory tree that has already been summarized."""
        from pathlib import Path
        from .source_scan import build_tree

        return build_tree(Path(root_path), max_entries=260)

    @tool
    def read_file(path: str) -> str:
        """Read a source file by repository-relative path."""
        from pathlib import Path

        root = Path(root_path).resolve()
        target = (root / path).resolve()
        if not str(target).startswith(str(root)):
            return "拒绝读取仓库之外的文件。"
        if not target.exists() or not target.is_file():
            return "文件不存在。"
        return read_text(target, max_chars=24_000)

    @tool
    def search_repo(query: str) -> str:
        """Search source files for a keyword and return file:line snippets."""
        from pathlib import Path

        return search_code(Path(root_path), query, limit=30)

    system_prompt = """
你是 project-helper 的源码问答 Agent。回答必须基于工具读取到的源码，不要凭空猜。
需要时先 search_repo，再 read_file。用中文回答，给出关键文件路径和下一步阅读建议。
"""
    tools = [list_tree, read_file, search_repo]
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=False)
