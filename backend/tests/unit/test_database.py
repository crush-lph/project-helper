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


def test_source_annotations_round_trip_and_project_isolation(tmp_path):
    db = Database(tmp_path / "project_helper.sqlite3")
    db.upsert_project(sample_project(id="project-1", repo_url="https://github.com/owner/one", name="one"))
    db.upsert_project(sample_project(id="project-2", repo_url="https://github.com/owner/two", name="two"))

    file_note = db.create_source_annotation(
        project_id="project-1",
        path="app/main.py",
        line=None,
        body="入口文件",
    )
    line_note = db.create_source_annotation(
        project_id="project-1",
        path="app/main.py",
        line=2,
        body="健康检查返回值",
    )
    db.create_source_annotation(
        project_id="project-2",
        path="app/main.py",
        line=1,
        body="另一个项目的批注",
    )

    listed = db.list_source_annotations("project-1", "app/main.py")

    assert [item["id"] for item in listed] == [file_note["id"], line_note["id"]]
    assert listed[0]["line"] is None
    assert listed[1]["line"] == 2
    assert all(item["project_id"] == "project-1" for item in listed)

    updated = db.update_source_annotation(
        project_id="project-1",
        annotation_id=line_note["id"],
        body="已确认健康检查",
    )

    assert updated["body"] == "已确认健康检查"
    assert updated["path"] == "app/main.py"
    assert db.update_source_annotation(project_id="project-2", annotation_id=line_note["id"], body="nope") is None
    assert db.delete_source_annotation(project_id="project-1", annotation_id=line_note["id"]) is True
    assert db.delete_source_annotation(project_id="project-1", annotation_id=line_note["id"]) is False
    assert [item["id"] for item in db.list_source_annotations("project-1", "app/main.py")] == [file_note["id"]]


def test_source_annotations_are_deleted_with_project(tmp_path):
    db = Database(tmp_path / "project_helper.sqlite3")
    db.upsert_project(sample_project())
    note = db.create_source_annotation(project_id="project-1", path="app/main.py", line=1, body="note")

    assert db.list_source_annotations("project-1")[0]["id"] == note["id"]

    db.delete_project("project-1")

    assert db.list_source_annotations("project-1") == []
