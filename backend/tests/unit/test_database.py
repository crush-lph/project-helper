import sqlite3

from app.database import Database


DEFAULT_USER = "test-user"


def sample_project(**overrides):
    project = {
        "id": "project-1",
        "user_id": DEFAULT_USER,
        "repo_url": "https://github.com/owner/repo",
        "name": "repo",
        "local_path": "/tmp/repo",
        "status": "created",
    }
    project.update(overrides)
    return project


def _create_user(db, username="testuser"):
    db.create_user(username, "secret-1")
    user = db.verify_user_password(username, "secret-1")
    return user["id"]


def test_upsert_get_list_and_save_analysis_round_trip(tmp_path):
    db = Database(tmp_path / "project_helper.sqlite3")
    user_id = _create_user(db)

    created = db.upsert_project_for_user(user_id, sample_project(user_id=user_id, summary={"file_count": 1, "stack": ["Python"]}))
    assert created["status"] == "created"
    assert created["summary"]["file_count"] == 1

    db.update_status("project-1", "scanning")
    assert db.get_project_for_user("project-1", user_id)["status"] == "scanning"

    db.save_analysis("project-1", "# Report", {"file_count": 2, "stack": ["FastAPI"], "llm": "local"})
    saved = db.get_project_by_repo_for_user("https://github.com/owner/repo", user_id)
    assert saved["status"] == "ready"
    assert saved["report"] == "# Report"
    assert saved["summary"]["stack"] == ["FastAPI"]

    listed = db.list_projects_for_user(user_id, include_report=False)
    assert listed[0]["report"] == ""
    assert listed[0]["summary"] == {"file_count": 2, "stack": ["FastAPI"], "llm": "local"}


def test_upsert_existing_repo_preserves_existing_status_and_report(tmp_path):
    db = Database(tmp_path / "project_helper.sqlite3")
    user_id = _create_user(db)

    db.upsert_project_for_user(user_id, sample_project(user_id=user_id))
    db.save_analysis("project-1", "# Old report", {"file_count": 5})

    updated = db.upsert_project_for_user(user_id, sample_project(user_id=user_id, name="renamed", local_path="/tmp/new"))

    assert updated["name"] == "renamed"
    assert updated["local_path"] == "/tmp/new"
    assert updated["status"] == "ready"
    assert updated["report"] == "# Old report"


def test_pin_order_and_delete_project(tmp_path):
    db = Database(tmp_path / "project_helper.sqlite3")
    user_id = _create_user(db)

    db.upsert_project_for_user(user_id, sample_project(id="project-1", user_id=user_id, repo_url="https://github.com/owner/one", name="one"))
    db.upsert_project_for_user(user_id, sample_project(id="project-2", user_id=user_id, repo_url="https://github.com/owner/two", name="two"))

    pinned = db.set_pinned("project-1", True)

    assert pinned["pinned"] is True
    assert db.list_projects_for_user(user_id, include_report=False)[0]["id"] == "project-1"

    unpinned = db.set_pinned("project-1", False)

    assert unpinned["pinned"] is False
    assert unpinned["pinned_at"] is None
    assert db.delete_project("project-1") is True
    assert db.get_project_for_user("project-1", user_id) is None
    assert db.delete_project("project-1") is False


def test_source_annotations_round_trip_and_project_isolation(tmp_path):
    db = Database(tmp_path / "project_helper.sqlite3")
    uid = _create_user(db)
    db.upsert_project_for_user(uid, sample_project(id="project-1", user_id=uid, repo_url="https://github.com/owner/one", name="one"))
    db.upsert_project_for_user(uid, sample_project(id="project-2", user_id=uid, repo_url="https://github.com/owner/two", name="two"))

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
    uid = _create_user(db)
    db.upsert_project_for_user(uid, sample_project(user_id=uid))
    note = db.create_source_annotation(project_id="project-1", path="app/main.py", line=1, body="note")

    assert db.list_source_annotations("project-1")[0]["id"] == note["id"]

    db.delete_project("project-1")

    assert db.list_source_annotations("project-1") == []


def test_users_sessions_and_projects_are_isolated_by_user(tmp_path):
    db = Database(tmp_path / "project_helper.sqlite3")
    alice = db.create_user("alice", "secret-1")
    bob = db.create_user("bob", "secret-2")

    assert db.verify_user_password("alice", "wrong") is None
    assert db.verify_user_password("alice", "secret-1")["id"] == alice["id"]

    token = db.create_session(alice["id"])
    assert db.get_user_by_session(token)["username"] == "alice"

    alice_project = db.upsert_project_for_user(
        alice["id"],
        sample_project(id="alice-project", user_id=alice["id"], repo_url="https://github.com/owner/repo"),
    )
    bob_project = db.upsert_project_for_user(
        bob["id"],
        sample_project(id="bob-project", user_id=bob["id"], repo_url="https://github.com/owner/repo"),
    )

    assert alice_project["id"] != bob_project["id"]
    assert alice_project["user_id"] == alice["id"]
    assert bob_project["user_id"] == bob["id"]
    assert [project["id"] for project in db.list_projects_for_user(alice["id"])] == [alice_project["id"]]
    assert [project["id"] for project in db.list_projects_for_user(bob["id"])] == [bob_project["id"]]
    assert db.get_project_for_user(alice_project["id"], bob["id"]) is None


def test_legacy_project_migration_preserves_annotations_and_chat(tmp_path):
    db_path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            repo_url TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            local_path TEXT NOT NULL,
            status TEXT NOT NULL,
            report TEXT NOT NULL DEFAULT '',
            summary_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE source_annotations (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            path TEXT NOT NULL,
            line INTEGER,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE chat_messages (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            role TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("legacy-project", "https://github.com/owner/repo", "repo", "/tmp/repo", "ready", "", "{}", "1", "1"),
    )
    conn.execute(
        "INSERT INTO source_annotations VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("note-1", "legacy-project", "app/main.py", 1, "legacy note", "1", "1"),
    )
    conn.execute(
        "INSERT INTO chat_messages VALUES (?, ?, ?, ?, ?)",
        ("message-1", "legacy-project", "user", "legacy question", "1"),
    )
    conn.commit()
    conn.close()

    db = Database(db_path)

    project = db.get_project_for_user("legacy-project", "default-user")
    assert project["user_id"] == "default-user"
    assert db.list_source_annotations("legacy-project")[0]["body"] == "legacy note"
    assert db.list_chat_messages("legacy-project")[0]["text"] == "legacy question"
