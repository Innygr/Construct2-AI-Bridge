"""Persistent local queue for user-supervised browser AI requests."""
from __future__ import annotations

import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

_DEFAULT_DB = Path(os.environ.get(
    "C2AI_COORDINATION_DB",
    str(Path.home() / ".construct2-ai-bridge" / "coordination.sqlite3"),
))
_PROVIDERS = {"any", "chatgpt", "claude", "gemini"}


class AIRequestError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class AIRequestStore:
    """SQLite-backed request mailbox shared by Construct 2 and the browser extension."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""
                CREATE TABLE IF NOT EXISTS ai_requests (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    system TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    response TEXT,
                    error TEXT,
                    claimed_by TEXT,
                    claimed_provider TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS ai_requests_status_idx ON ai_requests(status, created_at)")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        return db

    @staticmethod
    def _public(row: sqlite3.Row, include_prompt: bool = True) -> dict[str, Any]:
        result = dict(row)
        if not include_prompt:
            result.pop("prompt", None)
            result.pop("system", None)
            result.pop("response", None)
        return result

    def create(self, provider: str, prompt: str, system: str) -> dict[str, Any]:
        if provider not in _PROVIDERS:
            raise AIRequestError("Unsupported provider.")
        now = time.time()
        request_id = "AI-" + uuid.uuid4().hex[:12].upper()
        with self._connect() as db:
            db.execute(
                """INSERT INTO ai_requests
                   (id,provider,prompt,system,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (request_id, provider, prompt, system, "pending", now, now),
            )
            row = db.execute("SELECT * FROM ai_requests WHERE id=?", (request_id,)).fetchone()
        return self._public(row)

    def list_pending(self, client_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT * FROM ai_requests
                   WHERE status='pending' OR (status='claimed' AND claimed_by=?)
                   ORDER BY created_at ASC LIMIT ?""",
                (client_id, limit),
            ).fetchall()
        return [self._public(row, include_prompt=False) | {
            "prompt": row["prompt"], "system": row["system"]
        } for row in rows]

    def get(self, request_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM ai_requests WHERE id=?", (request_id,)).fetchone()
        if row is None:
            raise AIRequestError("AI request not found.", 404)
        return self._public(row)

    def claim(self, request_id: str, client_id: str, provider: str) -> dict[str, Any]:
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM ai_requests WHERE id=?", (request_id,)).fetchone()
            if row is None:
                raise AIRequestError("AI request not found.", 404)
            if provider not in _PROVIDERS - {"any"}:
                raise AIRequestError("Unsupported browser provider.")
            if row["provider"] not in ("any", provider):
                raise AIRequestError("This request was addressed to a different AI provider.", 409)
            if row["status"] == "claimed" and row["claimed_by"] == client_id:
                return self._public(row)
            if row["status"] != "pending":
                raise AIRequestError(f"AI request is already {row['status']}.", 409)
            db.execute(
                """UPDATE ai_requests SET status='claimed',claimed_by=?,
                   claimed_provider=?,updated_at=? WHERE id=?""",
                (client_id, provider, now, request_id),
            )
            row = db.execute("SELECT * FROM ai_requests WHERE id=?", (request_id,)).fetchone()
        return self._public(row)

    def complete(self, request_id: str, client_id: str, provider: str, response: str) -> dict[str, Any]:
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM ai_requests WHERE id=?", (request_id,)).fetchone()
            if row is None:
                raise AIRequestError("AI request not found.", 404)
            if row["status"] != "claimed" or row["claimed_by"] != client_id:
                raise AIRequestError("This browser connector does not own the active request.", 409)
            if row["claimed_provider"] != provider:
                raise AIRequestError("The response provider does not match the claimed provider.", 409)
            db.execute(
                "UPDATE ai_requests SET status='completed',response=?,updated_at=? WHERE id=?",
                (response, now, request_id),
            )
            row = db.execute("SELECT * FROM ai_requests WHERE id=?", (request_id,)).fetchone()
        return self._public(row)

    def fail(self, request_id: str, client_id: str, error: str) -> dict[str, Any]:
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM ai_requests WHERE id=?", (request_id,)).fetchone()
            if row is None:
                raise AIRequestError("AI request not found.", 404)
            if row["status"] != "claimed" or row["claimed_by"] != client_id:
                raise AIRequestError("This browser connector does not own the active request.", 409)
            db.execute(
                "UPDATE ai_requests SET status='failed',error=?,updated_at=? WHERE id=?",
                (error, now, request_id),
            )
            row = db.execute("SELECT * FROM ai_requests WHERE id=?", (request_id,)).fetchone()
        return self._public(row)

    def cancel(self, request_id: str) -> dict[str, Any]:
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM ai_requests WHERE id=?", (request_id,)).fetchone()
            if row is None:
                raise AIRequestError("AI request not found.", 404)
            if row["status"] not in ("completed", "failed", "cancelled"):
                db.execute("UPDATE ai_requests SET status='cancelled',updated_at=? WHERE id=?", (now, request_id))
                row = db.execute("SELECT * FROM ai_requests WHERE id=?", (request_id,)).fetchone()
        return self._public(row)
