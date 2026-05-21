import asyncio
import time

from langgraph.errors import GraphRecursionError

from app.agents.code_agent import stream_agent_events
from app.agents.report_agent import local_report
from app.config import Settings
from app.database import Database
from app.services import analysis as analysis_service
from app.services.analysis import analyze_project_stream
from app.services.chat import chat_stream
from app.utils.sse import sse


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


def test_stream_agent_events_sets_higher_recursion_limit():
    class FakeAgent:
        def __init__(self):
            self.config = None

        async def astream_events(self, input_msg, config=None, version=None):
            self.config = config
            if False:
                yield {}

    agent = FakeAgent()

    async def collect():
        return [event async for event in stream_agent_events(agent, "question", thread_id="proj-1")]

    asyncio.run(collect())

    assert agent.config["configurable"]["thread_id"] == "proj-1"
    assert agent.config["recursion_limit"] == 80


def test_chat_stream_reports_recursion_limit_as_actionable_error(monkeypatch, tmp_path):
    class LoopingAgent:
        async def astream_events(self, input_msg, config=None, version=None):
            raise GraphRecursionError("Recursion limit of 25 reached without hitting a stop condition.")
            if False:
                yield {}

    from app.services import chat as chat_service
    monkeypatch.setattr(chat_service, "create_code_agent", lambda settings, root_path: LoopingAgent())
    settings = Settings(deepseek_api_key="test-key", data_dir=tmp_path / "data")
    project = {"local_path": str(tmp_path), "id": "proj-1"}

    async def collect():
        return [chunk async for chunk in chat_stream(settings, project, "分析 React 仓库")]

    chunks = asyncio.run(collect())

    assert chunks[0].startswith("event: failed")
    assert "Agent 检索步数过多" in chunks[0]
    assert "缩小问题范围" in chunks[0]


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
    db.create_user("testuser", "secret-1")
    user = db.verify_user_password("testuser", "secret-1")
    uid = user["id"]
    project = db.upsert_project_for_user(
        uid,
        {
            "id": "project-1",
            "user_id": uid,
            "repo_url": "https://github.com/owner/repo",
            "name": "repo",
            "local_path": str(repo_root),
            "status": "created",
        },
    )
    monkeypatch.setattr(analysis_service, "clone_or_update", fake_clone_or_update)

    async def collect():
        return [chunk async for chunk in analyze_project_stream(db, settings, project)]

    async def run_pair():
        return await asyncio.gather(collect(), collect())

    first, second = asyncio.run(run_pair())

    assert calls == 1
    assert any(chunk.startswith("event: done") for chunk in first)
    assert second[0].startswith("event: cached")
