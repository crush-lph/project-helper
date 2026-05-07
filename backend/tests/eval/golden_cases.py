"""Golden test cases for report and chat quality evaluation."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReportTestCase:
    name: str
    repo_url: str
    summary: dict
    required_sections: list[str]
    expected_file_refs: list[str] = field(default_factory=list)
    forbidden_phrases: list[str] = field(default_factory=list)


@dataclass
class ChatTestCase:
    name: str
    question: str
    expected_keywords: list[str]
    local_path_setup: dict[str, str] = field(default_factory=dict)


REPORT_SECTIONS = [
    "项目概述",
    "技术栈",
    "目录结构",
    "核心入口",
    "核心模块",
    "关键函数",
    "数据流",
    "设计模式",
    "新手阅读路线",
    "可以继续追问",
]

PYTHON_FASTAPI_CASE = ReportTestCase(
    name="python_fastapi_project",
    repo_url="https://github.com/owner/fastapi-app",
    summary={
        "file_count": 5,
        "stack": ["FastAPI", "Python"],
        "entrypoints": ["app/main.py"],
        "core_files": ["app/main.py", "app/config.py", "requirements.txt"],
        "symbols": ["app/main.py: health, startup", "app/config.py: Settings"],
        "extensions": {".py": 3, ".txt": 1, ".md": 1},
        "readme": "# FastAPI App\nA simple API service.",
        "tree": "app/\n  main.py\n  config.py\nrequirements.txt\nREADME.md",
    },
    required_sections=REPORT_SECTIONS,
    expected_file_refs=["app/main.py"],
    forbidden_phrases=["我不确定", "无法分析"],
)

NODE_VUE_CASE = ReportTestCase(
    name="node_vue_project",
    repo_url="https://github.com/owner/vue-app",
    summary={
        "file_count": 8,
        "stack": ["Vue", "Node.js", "Vite"],
        "entrypoints": ["src/main.ts", "src/App.vue"],
        "core_files": ["src/main.ts", "src/App.vue", "package.json", "vite.config.ts"],
        "symbols": ["src/main.ts: createApp", "src/App.vue: setup"],
        "extensions": {".vue": 3, ".ts": 4, ".json": 1},
        "readme": "# Vue App\nFrontend project.",
        "tree": "src/\n  main.ts\n  App.vue\n  components/\npackage.json\nvite.config.ts",
    },
    required_sections=REPORT_SECTIONS,
    expected_file_refs=["src/App.vue"],
    forbidden_phrases=["我不确定", "无法分析"],
)

MINIMAL_REPO_CASE = ReportTestCase(
    name="minimal_readme_only",
    repo_url="https://github.com/owner/empty-project",
    summary={
        "file_count": 1,
        "stack": [],
        "entrypoints": [],
        "core_files": ["README.md"],
        "symbols": [],
        "extensions": {".md": 1},
        "readme": "# Empty Project\nNothing here yet.",
        "tree": "README.md",
    },
    required_sections=["项目概述", "技术栈", "目录结构"],
    forbidden_phrases=["我不确定"],
)

REPORT_CASES = [PYTHON_FASTAPI_CASE, NODE_VUE_CASE, MINIMAL_REPO_CASE]

CHAT_CASES = [
    ChatTestCase(
        name="find_entrypoint",
        question="main.py",
        expected_keywords=["main.py"],
        local_path_setup={
            "app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
            "README.md": "# Test\n",
        },
    ),
    ChatTestCase(
        name="search_function",
        question="health 函数在哪里定义的？",
        expected_keywords=["main.py", "health"],
        local_path_setup={
            "app/main.py": "def health():\n    return {'ok': True}\n",
            "README.md": "# Test\n",
        },
    ),
]
