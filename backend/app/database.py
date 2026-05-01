import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
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

    @staticmethod
    def _row_to_project(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["summary"] = json.loads(data.pop("summary_json") or "{}")
        data["pinned"] = bool(data.get("pinned_at"))
        return data
