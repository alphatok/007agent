"""Session and message persistence using SQLite.

Design inspired by Codex CLI (session-based persistence) and Claude Code
(local file storage), implemented with SQLite for zero-config single-machine
deployment.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentscope.agent import Agent


def _now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    """SQLite-backed session and message persistence.

    Usage::

        store = SessionStore("data/agent.db")
        session_id = store.create_session(name="my-session")
        store.save_message(session_id, "user", "Hello!")
        store.load_session(session_id, agent)
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._create_tables()

    def _create_tables(self) -> None:
        """Create tables if they don't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                model TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                summary TEXT,
                message_count INTEGER DEFAULT 0,
                token_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_calls TEXT,
                tool_call_id TEXT,
                token_count INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS tool_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                tool_name TEXT NOT NULL,
                tool_input TEXT,
                tool_output TEXT,
                status TEXT NOT NULL,
                duration_ms INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id),
                FOREIGN KEY (message_id) REFERENCES messages(id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_tool_logs_session
                ON tool_logs(session_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_sessions_updated
                ON sessions(updated_at DESC);
        """)
        self._conn.commit()

    # ---- Session CRUD ----

    def create_session(self, name: str | None = None) -> str:
        """Create a new session, return session_id."""
        session_id = str(uuid.uuid4())
        now = _now()
        self._conn.execute(
            """INSERT INTO sessions (id, name, created_at, updated_at)
               VALUES (?, ?, ?, ?)""",
            (session_id, name or f"Session {now[:19]}", now, now),
        )
        self._conn.commit()
        return session_id

    def list_sessions(self, status: str = "active",
                      limit: int = 50) -> list[dict]:
        """List sessions ordered by updated_at descending."""
        rows = self._conn.execute(
            """SELECT * FROM sessions
               WHERE status = ?
               ORDER BY updated_at DESC
               LIMIT ?""",
            (status, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: str) -> dict | None:
        """Get session metadata by ID."""
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its messages. Returns True if deleted."""
        session = self.get_session(session_id)
        if session is None:
            return False
        self._conn.execute(
            "DELETE FROM tool_logs WHERE session_id = ?", (session_id,)
        )
        self._conn.execute(
            "DELETE FROM messages WHERE session_id = ?", (session_id,)
        )
        self._conn.execute(
            "DELETE FROM sessions WHERE id = ?", (session_id,)
        )
        self._conn.commit()
        return True

    def cleanup_old_sessions(self, max_count: int,
                             max_age_days: int) -> int:
        """Remove sessions exceeding max_count or older than max_age_days."""
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) -
                  timedelta(days=max_age_days)).isoformat()

        deleted = 0

        # Delete by age
        age_rows = self._conn.execute(
            "SELECT id FROM sessions WHERE updated_at < ?", (cutoff,)
        ).fetchall()
        for row in age_rows:
            self._delete_session_cascade(row["id"])
            deleted += 1

        # Delete by count (keep most recent max_count)
        current_count = self._conn.execute(
            "SELECT COUNT(*) FROM sessions"
        ).fetchone()[0]
        if current_count > max_count:
            old = self._conn.execute(
                """SELECT id FROM sessions
                   ORDER BY updated_at DESC
                   LIMIT -1 OFFSET ?""",
                (max_count,),
            ).fetchall()
            for row in old:
                self._delete_session_cascade(row["id"])
                deleted += 1

        self._conn.commit()
        return deleted

    def _delete_session_cascade(self, session_id: str) -> None:
        """Delete a session and all associated data."""
        self._conn.execute(
            "DELETE FROM tool_logs WHERE session_id = ?", (session_id,)
        )
        self._conn.execute(
            "DELETE FROM messages WHERE session_id = ?", (session_id,)
        )
        self._conn.execute(
            "DELETE FROM sessions WHERE id = ?", (session_id,)
        )

    # ---- Message CRUD ----

    def save_message(self, session_id: str, role: str, content: str,
                     tool_calls: list | None = None,
                     tool_call_id: str | None = None,
                     token_count: int = 0) -> int:
        """Save a message and update session metadata."""
        now = _now()
        tool_calls_json = (
            json.dumps(tool_calls, ensure_ascii=False)
            if tool_calls else None
        )
        cur = self._conn.execute(
            """INSERT INTO messages
               (session_id, role, content, tool_calls, tool_call_id,
                token_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, role, content, tool_calls_json,
             tool_call_id, token_count, now),
        )
        self._conn.execute(
            """UPDATE sessions
               SET updated_at = ?, message_count = message_count + 1
               WHERE id = ?""",
            (now, session_id),
        )
        self._conn.commit()
        return cur.lastrowid or 0

    def save_tool_log(self, session_id: str, message_id: int,
                      tool_name: str, tool_input: str,
                      tool_output: str, status: str,
                      duration_ms: int = 0) -> int:
        """Save a tool execution log entry."""
        cur = self._conn.execute(
            """INSERT INTO tool_logs
               (session_id, message_id, tool_name, tool_input,
                tool_output, status, duration_ms, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, message_id, tool_name, tool_input,
             tool_output, status, duration_ms, _now()),
        )
        self._conn.commit()
        return cur.lastrowid or 0

    def get_messages(self, session_id: str, limit: int | None = None,
                     offset: int = 0) -> list[dict]:
        """Get messages for a session, ordered by created_at."""
        sql = """SELECT * FROM messages
                 WHERE session_id = ?
                 ORDER BY created_at ASC"""
        params: list = [session_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        if offset:
            sql += " OFFSET ?"
            params.append(offset)
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_message_count(self, session_id: str) -> int:
        """Get total message count for a session."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row[0] if row else 0

    # ---- Summary ----

    def save_summary(self, session_id: str, summary: str) -> None:
        """Save a session summary."""
        self._conn.execute(
            "UPDATE sessions SET summary = ?, updated_at = ? WHERE id = ?",
            (summary, _now(), session_id),
        )
        self._conn.commit()

    def get_summary(self, session_id: str) -> str | None:
        """Get session summary."""
        row = self._conn.execute(
            "SELECT summary FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return row["summary"] if row else None

    # ---- Session Recovery ----

    def load_session(self, session_id: str, agent: "Agent") -> bool:
        """Load historical messages into agent.state.context."""
        from agentscope.message import Msg, TextBlock

        messages = self.get_messages(session_id)
        if not messages:
            return False

        for msg in messages:
            agent_msg = Msg(
                name=msg["role"],
                content=[TextBlock(text=msg["content"])],
                role=msg["role"],
            )
            agent.state.context.append(agent_msg)

        return True

    def resume_last_session(self, agent: "Agent") -> str | None:
        """Resume the most recent session, return session_id or None."""
        sessions = self.list_sessions(limit=1)
        if not sessions:
            return None
        session_id = sessions[0]["id"]
        self.load_session(session_id, agent)
        return session_id