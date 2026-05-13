from __future__ import annotations

import json
import logging
from typing import Any, cast

from pydantic import BaseModel, Field

from ..config import Settings
from ..llm import get_llm
from ..prompts.manager import PromptManager

logger = logging.getLogger(__name__)

_prompts = PromptManager()


# ---- 结构化输出 Schema ----

class ReportSection(BaseModel):
    title: str = Field(description="章节标题")
    content: str = Field(description="章节内容（Markdown）")


class ReportOutput(BaseModel):
    overview: ReportSection = Field(description="项目概述")
    tech_stack: ReportSection = Field(description="技术栈")
    directory_structure: ReportSection = Field(description="目录结构")
    core_modules: ReportSection = Field(description="核心模块")
    data_flow: ReportSection = Field(description="数据流")
    design_patterns: ReportSection = Field(description="设计模式与工程实践")
    reading_path: ReportSection = Field(description="新手阅读路线")
    follow_up_questions: list[str] = Field(description="可继续追问的问题列表")


# ---- 报告生成 ----

def build_report_prompt(repo_url: str, summary: dict[str, Any]) -> str:
    return _prompts.render("report_prompt", repo_url=repo_url, summary=summary)


def _parse_report_output(raw: str) -> ReportOutput | None:
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and all(k in data for k in ReportOutput.model_fields):
            return ReportOutput(**data)
        return None
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def generate_llm_report(settings: Settings, repo_url: str, summary: dict[str, Any]) -> str | None:
    """三层 Fallback 报告生成：structured output → raw prompt → None。"""
    llm = get_llm(settings)
    if llm is None:
        return None

    result: ReportOutput | None = None

    # Layer 1: structured output (json_mode)
    try:
        structured_llm = llm.with_structured_output(ReportOutput, method="json_mode")
        structured_result = structured_llm.invoke(build_report_prompt(repo_url, summary))
        result = cast(ReportOutput, structured_result)
    except Exception:
        logger.warning("structured output failed, falling back to raw prompt", exc_info=True)

    # Layer 2: raw prompt + JSON schema
    if result is None:
        try:
            llm_no_tool = get_llm(settings)
            if llm_no_tool:
                prompt = build_report_prompt(repo_url, summary) + (
                    '\n\n请严格按照以下 JSON 格式输出（不要 Markdown 代码块包裹）：\n'
                    + ReportOutput.model_json_schema().__str__()
                )
                raw = llm_no_tool.invoke(prompt).content
                if isinstance(raw, str):
                    result = _parse_report_output(raw)
        except Exception:
            logger.warning("fallback raw prompt also failed", exc_info=True)

    if result is None:
        return None

    sections = [
        result.overview,
        result.tech_stack,
        result.directory_structure,
        result.core_modules,
        result.data_flow,
        result.design_patterns,
        result.reading_path,
    ]
    body = "\n\n".join(f"## {s.title}\n\n{s.content}" for s in sections)
    questions = "\n".join(f"- {q}" for q in result.follow_up_questions)
    return f"{body}\n\n## 可以继续追问\n\n{questions}"


def local_report(repo_url: str, summary: dict[str, Any]) -> str:
    """无 LLM 时的确定性模板报告。"""
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

1. 阅读 README，先知道项目"解决什么问题"。
2. 打开入口文件，理解程序第一步做什么。
3. 浏览核心目录，不急着逐行看，先建立地图。
4. 挑一个功能，从路由/命令开始追到核心函数。
5. 用问答区提问，例如"用户请求从哪里进入？"、"某个配置项在哪里使用？"。

## 可以继续追问

- 这个项目启动流程是什么？
- 某个 API/命令的调用链是什么？
- 哪些文件最值得先读？
- 如果我要改一个功能，应该从哪里下手？
"""
