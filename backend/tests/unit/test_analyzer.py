import asyncio
import time

from app.agents.report_agent import local_report
from app.config import Settings
from app.database import Database
from app.services import analysis as analysis_service
from app.services.analysis import analyze_project_stream, make_analysis_locks, sse
from app.services.chat import chat_stream


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
    settings = Settings(deepseek_api_key="", data_dir=tmp_path / "data")
    project = {"local_path": str(tmp_path), "id": "proj-1"}

    async def collect():
        return [chunk async for chunk in chat_stream(settings, project, "startup 在哪里")]

    chunks = asyncio.run(collect())

    assert chunks[0].startswith("event: token")
    assert any("app/main.py:1" in chunk for chunk in chunks)
    assert chunks[-1] == "event: done\ndata: {}\n\n"


def test_chat_stream_yields_agent_steps_incrementally(monkeypatch, tmp_path):
    class FakeMessage:
        def __init__(self, content=""):
            self.content = content

    class FakeAgent:
        async def astream_events(self, input_msg, config=None, version=None):
            yield {"event": "on_tool_start", "name": "search_repo", "input": {"query": "test"}}
            yield {"event": "on_tool_end", "data": {"output": "file.py:1: def test()"}}
            yield {"event": "on_chat_model_stream", "data": {"chunk": FakeMessage("first")}}
            time.sleep(0.2)
            yield {"event": "on_chat_model_stream", "data": {"chunk": FakeMessage(" second")}}

    from app.services import chat as chat_service
    monkeypatch.setattr(chat_service, "create_code_agent", lambda settings, root_path: FakeAgent())
    settings = Settings(deepseek_api_key="test-key", data_dir=tmp_path / "data")
    project = {"local_path": str(tmp_path), "id": "proj-1"}

    async def collect_with_timing():
        stream = chat_stream(settings, project, "question")
        start = time.monotonic()
        first = await asyncio.wait_for(anext(stream), timeout=0.1)
        elapsed = time.monotonic() - start
        rest = [chunk async for chunk in stream]
        return first, elapsed, rest

    first, elapsed, rest = asyncio.run(collect_with_timing())

    assert first.startswith("event: agent")
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

    settings = Settings(deepseek_api_key="", data_dir=tmp_path / "data")
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
    monkeypatch.setattr(analysis_service, "clone_or_update", fake_clone_or_update)

    project_locks = make_analysis_locks()

    async def collect():
        return [chunk async for chunk in analyze_project_stream(db, settings, project, locks=project_locks)]

    async def run_pair():
        return await asyncio.gather(collect(), collect())

    first, second = asyncio.run(run_pair())

    assert calls == 1
    assert any(chunk.startswith("event: done") for chunk in first)
    assert second[0].startswith("event: cached")
