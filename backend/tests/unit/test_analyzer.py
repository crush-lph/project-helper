import asyncio
import time

from app import analyzer
from app.analyzer import analyze_project_stream, chat_stream, local_report, sse
from app.config import Settings
from app.database import Database


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


def test_chat_stream_yields_agent_steps_incrementally(monkeypatch, tmp_path):
    class FakeAgent:
        def stream(self, payload):
            yield {"output": "first"}
            time.sleep(0.2)
            yield {"output": "second"}

    monkeypatch.setattr(analyzer, "create_code_agent", lambda settings, root_path: FakeAgent())
    settings = Settings(deepseek_api_key="test-key", PROJECT_HELPER_DATA_DIR=tmp_path / "data")
    project = {"local_path": str(tmp_path)}

    async def collect_with_timing():
        stream = chat_stream(settings, project, "question")
        start = time.monotonic()
        first = await asyncio.wait_for(anext(stream), timeout=0.1)
        elapsed = time.monotonic() - start
        rest = [chunk async for chunk in stream]
        return first, elapsed, rest

    first, elapsed, rest = asyncio.run(collect_with_timing())

    assert first == 'event: token\ndata: {"text": "first\\n"}\n\n'
    assert elapsed < 0.1
    assert rest[-1] == "event: done\ndata: {}\n\n"


def test_analyze_stream_serializes_concurrent_runs_for_same_project(monkeypatch, tmp_path):
    calls = 0
    repo_root = tmp_path / "repo"

    def fake_clone_or_update(repo_url, root):
        nonlocal calls
        calls += 1
        time.sleep(0.05)
        root.mkdir(parents=True, exist_ok=True)
        (root / "README.md").write_text("# Demo\n", encoding="utf-8")

    settings = Settings(deepseek_api_key="", PROJECT_HELPER_DATA_DIR=tmp_path / "data")
    db = Database(settings.db_path)
    project = db.upsert_project(
        {
            "id": "project-1",
            "repo_url": "https://github.com/owner/repo",
            "name": "repo",
            "local_path": str(repo_root),
            "status": "created",
        }
    )
    monkeypatch.setattr(analyzer, "clone_or_update", fake_clone_or_update)

    async def collect():
        return [chunk async for chunk in analyze_project_stream(db, settings, project)]

    async def run_pair():
        return await asyncio.gather(collect(), collect())

    first, second = asyncio.run(run_pair())

    assert calls == 1
    assert any(chunk.startswith("event: done") for chunk in first)
    assert second[0].startswith("event: cached")
