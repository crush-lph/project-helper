from __future__ import annotations

import json
from pathlib import Path
from typing import Any, AsyncGenerator

from .config import Settings
from .database import Database
from .llm import create_code_agent, generate_llm_report
from .repository import clone_or_update
from .source_scan import scan_repository, search_code


def local_report(repo_url: str, summary: dict[str, Any]) -> str:
    stack = "、".join(summary.get("stack") or ["暂未从配置文件中明确识别"])
    entrypoints = "\n".join(f"- `{item}`" for item in summary.get("entrypoints", [])) or "- 暂未识别到典型入口文件"
    core_files = "\n".join(f"- `{item}`" for item in summary.get("core_files", [])[:18])
    symbols = "\n".join(f"- `{item}`" for item in summary.get("symbols", [])[:24]) or "- 暂未提取到明显函数/类符号"
    extensions = ", ".join(f"{key}: {value}" for key, value in summary.get("extensions", {}).items())
    readme = (summary.get("readme") or "").strip().splitlines()
    readme_hint = "\n".join(f"> {line[:180]}" for line in readme[:8]) if readme else "> 该仓库没有可读取的 README 摘要。"

    return f"""# project-helper 源码分析报告

## 项目概述

仓库：`{repo_url}`

从当前扫描结果看，这个项目一共有 **{summary.get("file_count", 0)}** 个可读源码/配置文件。新手可以先把它理解成三层：入口文件负责启动，核心目录承载业务逻辑，配置文件说明它依赖什么技术和怎样运行。

README 片段：

{readme_hint}

## 技术栈

识别到的主要技术：**{stack}**。

文件类型分布：`{extensions}`。

## 目录结构

```text
{summary.get("tree", "")}
```

## 核心入口

{entrypoints}

## 核心模块与重要文件

{core_files}

## 关键函数/类线索

{symbols}

## 数据流怎么读

1. 先找入口文件，看程序如何启动、路由如何注册、主流程如何接线。
2. 再看配置文件，例如 `package.json`、`pyproject.toml`、`requirements.txt`、`go.mod`，确认外部依赖。
3. 顺着入口引用到的模块往下读：路由/命令入口 -> service/usecase -> 数据访问/工具函数。
4. 遇到不懂的函数名，回到 project-helper 的问答区搜索它，让 Agent 帮你定位调用链。

## 设计模式与工程实践

从静态扫描推断，这个仓库可能采用了按目录分层、入口和业务逻辑分离、配置驱动依赖管理等常见工程实践。更细的模式需要结合具体文件继续阅读验证。

## 新手阅读路线

1. 阅读 README，先知道项目“解决什么问题”。
2. 打开入口文件，理解程序第一步做什么。
3. 浏览核心目录，不急着逐行看，先建立地图。
4. 挑一个功能，从路由/命令开始追到核心函数。
5. 用问答区提问，例如“用户请求从哪里进入？”、“某个配置项在哪里使用？”。

## 可以继续追问

- 这个项目启动流程是什么？
- 某个 API/命令的调用链是什么？
- 哪些文件最值得先读？
- 如果我要改一个功能，应该从哪里下手？
"""


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def analyze_project_stream(db: Database, settings: Settings, project: dict[str, Any]) -> AsyncGenerator[str, None]:
    if project["status"] == "ready" and project.get("report"):
        yield sse("cached", {"message": "命中缓存，直接返回上次分析结果。", "project_id": project["id"]})
        yield sse("done", {"project_id": project["id"]})
        return

    project_id = project["id"]
    root = Path(project["local_path"])
    try:
        db.update_status(project_id, "cloning")
        yield sse("progress", {"step": "clone", "message": "正在克隆或更新仓库..."})
        clone_or_update(project["repo_url"], root)

        db.update_status(project_id, "scanning")
        yield sse("progress", {"step": "scan", "message": "正在扫描目录、技术栈和核心文件..."})
        summary = scan_repository(root)

        db.update_status(project_id, "summarizing")
        yield sse("progress", {"step": "summarize", "message": "正在生成通俗版源码报告..."})
        report = generate_llm_report(settings, project["repo_url"], summary)
        if report is None:
            report = local_report(project["repo_url"], summary)
            summary["llm"] = "DEEPSEEK_API_KEY 未配置，已使用本地静态分析生成报告。"
        else:
            summary["llm"] = f"DeepSeek model: {settings.deepseek_model}"

        db.save_analysis(project_id, report, summary)
        yield sse("done", {"project_id": project_id})
    except Exception as exc:
        db.update_status(project_id, "failed")
        yield sse("failed", {"message": str(exc)})


async def chat_stream(settings: Settings, project: dict[str, Any], question: str) -> AsyncGenerator[str, None]:
    root = Path(project["local_path"])
    agent = create_code_agent(settings, str(root))
    if agent is None:
        yield sse("token", {"text": "当前未配置 DEEPSEEK_API_KEY，我先用本地搜索给你一个可验证答案。\n\n"})
        keywords = [part for part in question.replace("，", " ").replace("？", " ").split() if len(part) >= 2]
        query = keywords[0] if keywords else question[:20]
        hits = search_code(root, query, limit=12)
        answer = f"我搜索了关键词 `{query}`，找到这些线索：\n\n```text\n{hits}\n```\n\n建议你继续追问一个更具体的问题，例如“解释第一个文件的作用”或“沿着这个函数追调用链”。"
        for chunk in answer.splitlines(keepends=True):
            yield sse("token", {"text": chunk})
        yield sse("done", {})
        return

    try:
        for step in agent.stream({"input": question}):
            text = ""
            if "actions" in step:
                action_names = ", ".join(action.tool for action in step["actions"])
                text = f"正在调用工具：{action_names}"
            elif "steps" in step:
                text = "已读取相关源码片段。"
            elif "output" in step:
                text = str(step["output"])
            if text:
                yield sse("token", {"text": text + "\n"})
        yield sse("done", {})
    except Exception as exc:
        yield sse("failed", {"message": str(exc)})
