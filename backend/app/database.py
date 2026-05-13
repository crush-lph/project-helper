import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path | str, *, use_memory: bool = False):
        self._path: Path | str = path
        self._use_memory = use_memory
        if not use_memory:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect_path(self) -> str:
        if self._use_memory:
            return ":memory:"
        return str(self._path)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self._connect_path(), timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
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
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
            if "pinned_at" not in columns:
                conn.execute("ALTER TABLE projects ADD COLUMN pinned_at TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_repo_url ON projects(repo_url)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS source_annotations (
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
                CREATE INDEX IF NOT EXISTS idx_source_annotations_project_path
                ON source_annotations(project_id, path, line, created_at)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
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
                """
                CREATE INDEX IF NOT EXISTS idx_chat_messages_project
                ON chat_messages(project_id, created_at ASC)
                """
            )

    def upsert_project(self, project: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, repo_url, name, local_path, status, report, summary_json, created_at, updated_at)
                VALUES (:id, :repo_url, :name, :local_path, :status, :report, :summary_json, :created_at, :updated_at)
                ON CONFLICT(repo_url) DO UPDATE SET
                    name = excluded.name,
                    local_path = excluded.local_path,
                    updated_at = excluded.updated_at
                """,
                {
                    **project,
                    "report": project.get("report", ""),
                    "summary_json": json.dumps(project.get("summary", {}), ensure_ascii=False),
                    "created_at": project.get("created_at", now),
                    "updated_at": now,
                },
            )
            row = conn.execute("SELECT * FROM projects WHERE repo_url = ?", (project["repo_url"],)).fetchone()
        return self._row_to_project(row)

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return self._row_to_project(row) if row else None

    def get_project_by_repo(self, repo_url: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE repo_url = ?", (repo_url,)).fetchone()
        return self._row_to_project(row) if row else None

    def list_projects(self, include_report: bool = True) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM projects
                ORDER BY
                    CASE WHEN pinned_at IS NULL THEN 1 ELSE 0 END,
                    pinned_at DESC,
                    updated_at DESC
                """
            ).fetchall()
        projects = [self._row_to_project(row) for row in rows]
        if not include_report:
            for project in projects:
                project["report"] = ""
                project["summary"] = {
                    "file_count": project.get("summary", {}).get("file_count", 0),
                    "stack": project.get("summary", {}).get("stack", []),
                    "llm": project.get("summary", {}).get("llm", ""),
                }
        return projects

    def update_status(self, project_id: str, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), project_id),
            )

    def save_analysis(self, project_id: str, report: str, summary: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE projects
                SET status = 'ready', report = ?, summary_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (report, json.dumps(summary, ensure_ascii=False), utc_now(), project_id),
            )

    def set_pinned(self, project_id: str, pinned: bool) -> dict[str, Any] | None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE projects SET pinned_at = ?, updated_at = ? WHERE id = ?",
                (now if pinned else None, now, project_id),
            )
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return self._row_to_project(row) if row else None

    def delete_project(self, project_id: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return cursor.rowcount > 0

    def list_source_annotations(self, project_id: str, path: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM source_annotations WHERE project_id = ?"
        params: list[Any] = [project_id]
        if path is not None:
            query += " AND path = ?"
            params.append(path)
        query += " ORDER BY path ASC, COALESCE(line, 0) ASC, created_at ASC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_source_annotation(row) for row in rows]

    def create_source_annotation(
        self,
        *,
        project_id: str,
        path: str,
        line: int | None,
        body: str,
    ) -> dict[str, Any]:
        now = utc_now()
        annotation_id = uuid.uuid4().hex
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO source_annotations (id, project_id, path, line, body, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (annotation_id, project_id, path, line, body, now, now),
            )
            row = conn.execute("SELECT * FROM source_annotations WHERE id = ?", (annotation_id,)).fetchone()
        return self._row_to_source_annotation(row)

    def update_source_annotation(
        self,
        *,
        project_id: str,
        annotation_id: str,
        body: str,
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE source_annotations
                SET body = ?, updated_at = ?
                WHERE id = ? AND project_id = ?
                """,
                (body, utc_now(), annotation_id, project_id),
            )
            row = conn.execute(
                "SELECT * FROM source_annotations WHERE id = ? AND project_id = ?",
                (annotation_id, project_id),
            ).fetchone()
        return self._row_to_source_annotation(row) if row else None

    def delete_source_annotation(self, *, project_id: str, annotation_id: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM source_annotations WHERE id = ? AND project_id = ?",
                (annotation_id, project_id),
            )
        return cursor.rowcount > 0

    def list_chat_messages(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM chat_messages WHERE project_id = ? ORDER BY created_at ASC",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_chat_message(self, project_id: str, role: str, text: str) -> dict[str, Any]:
        now = utc_now()
        msg_id = uuid.uuid4().hex
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO chat_messages (id, project_id, role, text, created_at) VALUES (?, ?, ?, ?, ?)",
                (msg_id, project_id, role, text, now),
            )
        return {"id": msg_id, "project_id": project_id, "role": role, "text": text, "created_at": now}

    def clear_chat_messages(self, project_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM chat_messages WHERE project_id = ?", (project_id,))

    @staticmethod
    def _row_to_project(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["summary"] = json.loads(data.pop("summary_json") or "{}")
        data["pinned"] = bool(data.get("pinned_at"))
        return data

    @staticmethod
    def _row_to_source_annotation(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)
