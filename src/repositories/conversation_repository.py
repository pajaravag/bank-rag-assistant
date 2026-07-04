"""Repository pattern over conversation history (SQLite).

Persists every turn per session ID (FR5) and exposes the read paths
the chat service (last-N window) and analytics (full traversal) need.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.models import ChatTurn

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    sources     TEXT,
    latency_ms  INTEGER,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, id);
"""


class ConversationRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        sources: list[str] | None = None,
        latency_ms: int | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, sources, latency_ms) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, json.dumps(sources or []), latency_ms),
            )

    def last_n(self, session_id: str, n: int) -> list[ChatTurn]:
        """The N most recent turns of a session, in chronological order."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content, sources FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, n),
            ).fetchall()
        return [
            ChatTurn(role=r["role"], content=r["content"], sources=json.loads(r["sources"] or "[]"))
            for r in reversed(rows)
        ]

    def full_history(self, session_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content, sources, latency_ms, created_at FROM messages WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [dict(r, sources=json.loads(r["sources"] or "[]")) for r in rows]

    def all_messages(self) -> list[dict]:
        """Every message across sessions — the analytics input."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT session_id, role, content, sources, latency_ms, created_at FROM messages ORDER BY id"
            ).fetchall()
        return [dict(r, sources=json.loads(r["sources"] or "[]")) for r in rows]

    def session_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT session_id, MAX(id) AS last_id FROM messages GROUP BY session_id ORDER BY last_id DESC"
            ).fetchall()
        return [r["session_id"] for r in rows]
