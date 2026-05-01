import asyncio

from app.analyzer import chat_stream, local_report, sse
from app.config import Settings


def test_sse_formats_named_event_with_json_payload():
    assert sse("progress", {"message": "开始"}) == 'event: progress\ndata: {"message": "开始"}\n\n'


def test_local_report_contains_core_scan_sections():
    report = local_report(
        "https://github.com/owner/repo",
        {
            "file_count": 2,
            "stack": ["FastAPI"],
            "entrypoints": ["app/main.py"],
            "core_files": ["app/main.py"],
            "symbols": ["app/main.py: health"],
            "extensions": {".py": 1},
            "readme": "# Demo\nintro",
            "tree": "app/\n  main.py",
        },
    )

    assert "project-helper 源码分析报告" in report
    assert "FastAPI" in report
    assert "`app/main.py`" in report
    assert "app/main.py: health" in report


def test_chat_stream_without_llm_uses_local_search(tmp_path):
    source = tmp_path / "app" / "main.py"
    source.parent.mkdir()
    source.write_text("def startup():\n    return 'ready'\n", encoding="utf-8")
    settings = Settings(deepseek_api_key="", PROJECT_HELPER_DATA_DIR=tmp_path / "data")
    project = {"local_path": str(tmp_path)}

    async def collect():
        return [chunk async for chunk in chat_stream(settings, project, "startup 在哪里")]

    chunks = asyncio.run(collect())

    assert chunks[0].startswith("event: token")
    assert any("app/main.py:1" in chunk for chunk in chunks)
    assert chunks[-1] == "event: done\ndata: {}\n\n"
