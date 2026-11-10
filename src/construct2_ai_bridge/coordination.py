"""Persistent coordination primitives for multiple AI agents.

The coordination store is local to the bridge host. It does not contact agents;
agents poll the API and explicitly publish their updates.
"""
from __future__ import annotations

import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(os.environ.get(
    "C2AI_COORDINATION_DB",
    str(Path.home() / ".construct2-ai-bridge" / "coordination.sqlite3"),
))


class CoordinationError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class CoordinationStore:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        return db

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'open'
                        CHECK(status IN ('open','claimed','in_review','done','blocked')),
                    owner TEXT,
                    branch TEXT,
                    created_by TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    agent TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                );
                CREATE TABLE IF NOT EXISTS file_locks (
                    path TEXT PRIMARY KEY,
                    agent TEXT NOT NULL,
                    task_id TEXT,
                    token TEXT NOT NULL,
                    acquired_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_task_idx
                    ON messages(task_id, id);
                CREATE INDEX IF NOT EXISTS tasks_status_idx
                    ON tasks(status, updated_at);
            """)

    @staticmethod
    def _task(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    def create_task(self, title: str, description: str, created_by: str) -> dict[str, Any]:
        now = time.time()
        task_id = "C2-" + uuid.uuid4().hex[:8].upper()
        with self._connect() as db:
            db.execute(
                """INSERT INTO tasks
                   (id,title,description,created_by,created_at,updated_at)
                   VALUES(?,?,?,?,?,?)""",
                (task_id, title, description, created_by, now, now),
            )
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return self._task(row)

    def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as db:
            if status:
                rows = db.execute(
                    "SELECT * FROM tasks WHERE status=? ORDER BY created_at DESC", (status,)
                ).fetchall()
            else:
                rows = db.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
        return [self._task(row) for row in rows]

    def claim_task(self, task_id: str, agent: str, branch: str | None = None) -> dict[str, Any]:
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise CoordinationError("Task not found.", 404)
            if row["status"] == "done":
                raise CoordinationError("Completed tasks cannot be claimed.", 409)
            if row["owner"] and row["owner"] != agent and row["status"] in ("claimed", "in_review"):
                raise CoordinationError(f"Task is already owned by {row['owner']}.", 409)
            db.execute(
                """UPDATE tasks SET owner=?, branch=COALESCE(?,branch),
                   status='claimed', updated_at=?, version=version+1 WHERE id=?""",
                (agent, branch, now, task_id),
            )
            updated = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return self._task(updated)

    def update_task(self, task_id: str, agent: str, status: str, branch: str | None = None) -> dict[str, Any]:
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise CoordinationError("Task not found.", 404)
            if row["owner"] != agent and row["created_by"] != agent:
                raise CoordinationError("Only the task owner or creator can update this task.", 403)
            db.execute(
                """UPDATE tasks SET status=?, branch=COALESCE(?,branch),
                   updated_at=?, version=version+1 WHERE id=?""",
                (status, branch, now, task_id),
            )
            updated = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return self._task(updated)

    def post_message(self, agent: str, body: str, task_id: str | None = None) -> dict[str, Any]:
        now = time.time()
        with self._connect() as db:
            if task_id and db.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone() is None:
                raise CoordinationError("Task not found.", 404)
            cursor = db.execute(
                "INSERT INTO messages(task_id,agent,body,created_at) VALUES(?,?,?,?)",
                (task_id, agent, body, now),
            )
            row = db.execute("SELECT * FROM messages WHERE id=?", (cursor.lastrowid,)).fetchone()
        return dict(row)

    def list_messages(self, task_id: str | None = None, after_id: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            if task_id:
                rows = db.execute(
                    """SELECT * FROM messages WHERE task_id=? AND id>?
                       ORDER BY id LIMIT ?""", (task_id, after_id, limit)
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM messages WHERE id>? ORDER BY id LIMIT ?",
                    (after_id, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def acquire_lock(self, path: str, agent: str, task_id: str | None, ttl_seconds: int) -> dict[str, Any]:
        now = time.time()
        token = uuid.uuid4().hex
        expires = now + ttl_seconds
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM file_locks WHERE expires_at<=?", (now,))
            existing = db.execute("SELECT * FROM file_locks WHERE path=?", (path,)).fetchone()
            if existing and existing["agent"] != agent:
                raise CoordinationError(
                    f"File is locked by {existing['agent']} until {existing['expires_at']}.", 409
                )
            db.execute(
                """INSERT INTO file_locks(path,agent,task_id,token,acquired_at,expires_at)
                   VALUES(?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET
                   agent=excluded.agent, task_id=excluded.task_id, token=excluded.token,
                   acquired_at=excluded.acquired_at, expires_at=excluded.expires_at""",
                (path, agent, task_id, token, now, expires),
            )
        return {"path": path, "agent": agent, "task_id": task_id, "token": token, "expires_at": expires}

    def release_lock(self, path: str, agent: str, token: str) -> None:
        with self._connect() as db:
            cursor = db.execute(
                "DELETE FROM file_locks WHERE path=? AND agent=? AND token=?",
                (path, agent, token),
            )
            if cursor.rowcount != 1:
                raise CoordinationError("Lock not found, expired, or owned by another agent.", 409)

    def list_locks(self) -> list[dict[str, Any]]:
        now = time.time()
        with self._connect() as db:
            db.execute("DELETE FROM file_locks WHERE expires_at<=?", (now,))
            rows = db.execute("SELECT * FROM file_locks ORDER BY path").fetchall()
        return [dict(row) for row in rows]
