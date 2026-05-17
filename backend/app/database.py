import json
import hashlib
import hmac
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


DEFAULT_USER_ID = "default-user"
PASSWORD_ITERATIONS = 120_000


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
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            self._ensure_default_user(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'default-user',
                    repo_url TEXT NOT NULL,
                    name TEXT NOT NULL,
                    local_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    report TEXT NOT NULL DEFAULT '',
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id, repo_url)
                )
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
            if "user_id" not in columns:
                self._migrate_projects_to_users(conn)
                columns = {row["name"] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
            if "pinned_at" not in columns:
                conn.execute("ALTER TABLE projects ADD COLUMN pinned_at TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_user_repo ON projects(user_id, repo_url)")
            self._create_source_annotations_table(conn)
            self._create_chat_messages_table(conn)

    def _create_source_annotations_table(self, conn: sqlite3.Connection) -> None:
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

    def _create_chat_messages_table(self, conn: sqlite3.Connection) -> None:
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

    def _ensure_default_user(self, conn: sqlite3.Connection) -> None:
        now = utc_now()
        salt, password_hash = self._hash_password(secrets.token_urlsafe(24))
        conn.execute(
            """
            INSERT OR IGNORE INTO users (id, username, password_salt, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (DEFAULT_USER_ID, "default", salt, password_hash, now),
        )

    def _migrate_projects_to_users(self, conn: sqlite3.Connection) -> None:
        existing_tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        has_source_annotations = "source_annotations" in existing_tables
        has_chat_messages = "chat_messages" in existing_tables
        if has_source_annotations:
            conn.execute("CREATE TEMP TABLE source_annotations_backup AS SELECT * FROM source_annotations")
            conn.execute("DROP TABLE source_annotations")
        if has_chat_messages:
            conn.execute("CREATE TEMP TABLE chat_messages_backup AS SELECT * FROM chat_messages")
            conn.execute("DROP TABLE chat_messages")

        conn.execute("ALTER TABLE projects RENAME TO projects_legacy")
        conn.execute(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT 'default-user',
                repo_url TEXT NOT NULL,
                name TEXT NOT NULL,
                local_path TEXT NOT NULL,
                status TEXT NOT NULL,
                report TEXT NOT NULL DEFAULT '',
                summary_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                pinned_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, repo_url)
            )
            """
        )
        legacy_columns = {row["name"] for row in conn.execute("PRAGMA table_info(projects_legacy)").fetchall()}
        pinned_expr = "pinned_at" if "pinned_at" in legacy_columns else "NULL"
        conn.execute(
            f"""
            INSERT INTO projects (
                id, user_id, repo_url, name, local_path, status, report,
                summary_json, created_at, updated_at, pinned_at
            )
            SELECT
                id, ?, repo_url, name, local_path, status, report,
                summary_json, created_at, updated_at, {pinned_expr}
            FROM projects_legacy
            """,
            (DEFAULT_USER_ID,),
        )
        conn.execute("DROP TABLE projects_legacy")

        if has_source_annotations:
            self._create_source_annotations_table(conn)
            conn.execute(
                """
                INSERT INTO source_annotations (id, project_id, path, line, body, created_at, updated_at)
                SELECT id, project_id, path, line, body, created_at, updated_at
                FROM source_annotations_backup
                """
            )
            conn.execute("DROP TABLE source_annotations_backup")
        if has_chat_messages:
            self._create_chat_messages_table(conn)
            conn.execute(
                """
                INSERT INTO chat_messages (id, project_id, role, text, created_at)
                SELECT id, project_id, role, text, created_at
                FROM chat_messages_backup
                """
            )
            conn.execute("DROP TABLE chat_messages_backup")

    @staticmethod
    def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
        password_salt = salt or secrets.token_hex(16)
        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(password_salt),
            PASSWORD_ITERATIONS,
        ).hex()
        return password_salt, password_hash

    def create_user(self, username: str, password: str) -> dict[str, Any]:
        now = utc_now()
        user_id = uuid.uuid4().hex
        normalized_username = username.strip().lower()
        salt, password_hash = self._hash_password(password)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (id, username, password_salt, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, normalized_username, salt, password_hash, now),
            )
        return {"id": user_id, "username": normalized_username, "created_at": now}

    def verify_user_password(self, username: str, password: str) -> dict[str, Any] | None:
        normalized_username = username.strip().lower()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (normalized_username,)).fetchone()
        if not row:
            return None
        _, candidate_hash = self._hash_password(password, row["password_salt"])
        if not hmac.compare_digest(candidate_hash, row["password_hash"]):
            return None
        return {"id": row["id"], "username": row["username"], "created_at": row["created_at"]}

    def create_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
                (token, user_id, utc_now()),
            )
        return token

    def get_user_by_session(self, token: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT users.id, users.username, users.created_at
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ?
                """,
                (token,),
            ).fetchone()
        return dict(row) if row else None

    def upsert_project(self, project: dict[str, Any]) -> dict[str, Any]:
        return self.upsert_project_for_user(project.get("user_id", DEFAULT_USER_ID), project)

    def upsert_project_for_user(self, user_id: str, project: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, user_id, repo_url, name, local_path, status, report, summary_json, created_at, updated_at)
                VALUES (:id, :user_id, :repo_url, :name, :local_path, :status, :report, :summary_json, :created_at, :updated_at)
                ON CONFLICT(user_id, repo_url) DO UPDATE SET
                    name = excluded.name,
                    local_path = excluded.local_path,
                    updated_at = excluded.updated_at
                """,
                {
                    **project,
                    "user_id": user_id,
                    "report": project.get("report", ""),
                    "summary_json": json.dumps(project.get("summary", {}), ensure_ascii=False),
                    "created_at": project.get("created_at", now),
                    "updated_at": now,
                },
            )
            row = conn.execute(
                "SELECT * FROM projects WHERE user_id = ? AND repo_url = ?",
                (user_id, project["repo_url"]),
            ).fetchone()
        return self._row_to_project(row)

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return self._row_to_project(row) if row else None

    def get_project_for_user(self, project_id: str, user_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ? AND user_id = ?",
                (project_id, user_id),
            ).fetchone()
        return self._row_to_project(row) if row else None

    def get_project_by_repo(self, repo_url: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE repo_url = ?", (repo_url,)).fetchone()
        return self._row_to_project(row) if row else None

    def get_project_by_repo_for_user(self, repo_url: str, user_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE repo_url = ? AND user_id = ?",
                (repo_url, user_id),
            ).fetchone()
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

    def list_projects_for_user(self, user_id: str, include_report: bool = True) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM projects
                WHERE user_id = ?
                ORDER BY
                    CASE WHEN pinned_at IS NULL THEN 1 ELSE 0 END,
                    pinned_at DESC,
                    updated_at DESC
                """,
                (user_id,),
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
