import json

from fastapi.testclient import TestClient

from app import analyzer
from app.config import Settings
from app.database import Database
from app.main import app
import app.main as main_module


def parse_sse_events(text: str):
    events = []
    for frame in text.strip().split("\n\n"):
        lines = frame.splitlines()
        name = next(line.removeprefix("event:").strip() for line in lines if line.startswith("event:"))
        data = next(line.removeprefix("data:").strip() for line in lines if line.startswith("data:"))
        events.append((name, json.loads(data)))
    return events


def install_test_runtime(monkeypatch, tmp_path):
    settings = Settings(deepseek_api_key="", PROJECT_HELPER_DATA_DIR=tmp_path / "data")
    db = Database(settings.db_path)
    monkeypatch.setattr(main_module, "settings", settings)
    monkeypatch.setattr(main_module, "db", db)
    return settings, db


def fake_clone_or_update(repo_url, root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("# Demo repo\n", encoding="utf-8")
    (root / "requirements.txt").write_text("fastapi==0.115.6\n", encoding="utf-8")
    app_dir = root / "app"
    app_dir.mkdir(exist_ok=True)
    (app_dir / "main.py").write_text("def health():\n    return {'ok': True}\n", encoding="utf-8")


def test_project_create_analyze_cache_and_chat_flow(monkeypatch, tmp_path):
    settings, db = install_test_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(analyzer, "clone_or_update", fake_clone_or_update)
    monkeypatch.setattr(analyzer, "generate_llm_report", lambda settings, repo_url, summary: None)
    client = TestClient(app)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["llm_configured"] is False

    created = client.post("/api/projects", json={"repo_url": "https://github.com/owner/repo.git"})
    assert created.status_code == 200
    project = created.json()
    assert project["repo_url"] == "https://github.com/owner/repo"
    assert project["status"] == "created"
    assert project["local_path"] == str(settings.clone_dir / project["id"])

    stream = client.get(f"/api/projects/{project['id']}/analyze/stream")
    assert stream.status_code == 200
    events = parse_sse_events(stream.text)
    assert [name for name, _ in events] == ["progress", "progress", "progress", "done"]
    assert db.get_project(project["id"])["status"] == "ready"

    loaded = client.get(f"/api/projects/{project['id']}")
    assert loaded.status_code == 200
    assert "project-helper 源码分析报告" in loaded.json()["report"]
    assert loaded.json()["summary"]["stack"] == ["FastAPI", "Python"]

    source_tree = client.get(f"/api/projects/{project['id']}/source/tree")
    assert source_tree.status_code == 200
    assert source_tree.json()["tree"][0]["path"] == "app"
    assert source_tree.json()["tree"][0]["children"][0]["path"] == "app/main.py"

    source_file = client.get(f"/api/projects/{project['id']}/source/file", params={"path": "app/main.py"})
    assert source_file.status_code == 200
    assert source_file.json()["path"] == "app/main.py"
    assert "def health" in source_file.json()["content"]

    traversal = client.get(f"/api/projects/{project['id']}/source/file", params={"path": "../secrets.py"})
    assert traversal.status_code == 400
    assert "仓库之外" in traversal.json()["detail"]

    cached_stream = client.get(f"/api/projects/{project['id']}/analyze/stream")
    cached_events = parse_sse_events(cached_stream.text)
    assert [name for name, _ in cached_events] == ["cached", "done"]

    chat = client.post(f"/api/projects/{project['id']}/chat/stream", json={"question": "health 在哪里"})
    assert chat.status_code == 200
    assert "app/main.py:1" in chat.text
    assert "event: done" in chat.text

    listed = client.get("/api/projects")
    assert listed.status_code == 200
    assert listed.json()["projects"][0]["report"] == ""

    pinned = client.patch(f"/api/projects/{project['id']}/pin", json={"pinned": True})
    assert pinned.status_code == 200
    assert pinned.json()["pinned"] is True

    deleted = client.delete(f"/api/projects/{project['id']}")
    assert deleted.status_code == 204
    assert db.get_project(project["id"]) is None
    assert not (settings.clone_dir / project["id"]).exists()


def test_api_rejects_invalid_project_and_empty_chat(monkeypatch, tmp_path):
    install_test_runtime(monkeypatch, tmp_path)
    client = TestClient(app)

    invalid = client.post("/api/projects", json={"repo_url": "https://gitlab.com/owner/repo"})
    assert invalid.status_code == 400

    created = client.post("/api/projects", json={"repo_url": "https://github.com/owner/repo"})
    project_id = created.json()["id"]

    source_before_ready = client.get(f"/api/projects/{project_id}/source/tree")
    assert source_before_ready.status_code == 409

    empty_chat = client.post(f"/api/projects/{project_id}/chat/stream", json={"question": "   "})
    assert empty_chat.status_code == 400

    missing = client.get("/api/projects/missing")
    assert missing.status_code == 404

    missing_pin = client.patch("/api/projects/missing/pin", json={"pinned": True})
    assert missing_pin.status_code == 404

    missing_delete = client.delete("/api/projects/missing")
    assert missing_delete.status_code == 404
