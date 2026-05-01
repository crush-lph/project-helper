from app.database import Database


def sample_project(**overrides):
    project = {
        "id": "project-1",
        "repo_url": "https://github.com/owner/repo",
        "name": "repo",
        "local_path": "/tmp/repo",
        "status": "created",
    }
    project.update(overrides)
    return project


def test_upsert_get_list_and_save_analysis_round_trip(tmp_path):
    db = Database(tmp_path / "project_helper.sqlite3")

    created = db.upsert_project(sample_project(summary={"file_count": 1, "stack": ["Python"]}))
    assert created["status"] == "created"
    assert created["summary"]["file_count"] == 1

    db.update_status("project-1", "scanning")
    assert db.get_project("project-1")["status"] == "scanning"

    db.save_analysis("project-1", "# Report", {"file_count": 2, "stack": ["FastAPI"], "llm": "local"})
    saved = db.get_project_by_repo("https://github.com/owner/repo")
    assert saved["status"] == "ready"
    assert saved["report"] == "# Report"
    assert saved["summary"]["stack"] == ["FastAPI"]

    listed = db.list_projects(include_report=False)
    assert listed[0]["report"] == ""
    assert listed[0]["summary"] == {"file_count": 2, "stack": ["FastAPI"], "llm": "local"}


def test_upsert_existing_repo_preserves_existing_status_and_report(tmp_path):
    db = Database(tmp_path / "project_helper.sqlite3")
    db.upsert_project(sample_project())
    db.save_analysis("project-1", "# Old report", {"file_count": 5})

    updated = db.upsert_project(sample_project(name="renamed", local_path="/tmp/new"))

    assert updated["name"] == "renamed"
    assert updated["local_path"] == "/tmp/new"
    assert updated["status"] == "ready"
    assert updated["report"] == "# Old report"


def test_pin_order_and_delete_project(tmp_path):
    db = Database(tmp_path / "project_helper.sqlite3")
    db.upsert_project(sample_project(id="project-1", repo_url="https://github.com/owner/one", name="one"))
    db.upsert_project(sample_project(id="project-2", repo_url="https://github.com/owner/two", name="two"))

    pinned = db.set_pinned("project-1", True)

    assert pinned["pinned"] is True
    assert db.list_projects(include_report=False)[0]["id"] == "project-1"

    unpinned = db.set_pinned("project-1", False)

    assert unpinned["pinned"] is False
    assert unpinned["pinned_at"] is None
    assert db.delete_project("project-1") is True
    assert db.get_project("project-1") is None
    assert db.delete_project("project-1") is False
