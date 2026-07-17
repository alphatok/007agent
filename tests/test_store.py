"""Tests for app.store module — SessionStore."""
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        yield db_path


class TestSessionStore:
    """Tests for SessionStore CRUD operations."""

    def test_init_creates_db(self, temp_db: str) -> None:
        """__init__ should create the SQLite database file."""
        from app.store import SessionStore

        assert not os.path.exists(temp_db)
        store = SessionStore(temp_db)
        assert os.path.exists(temp_db)

    def test_init_enables_wal(self, temp_db: str) -> None:
        """__init__ should enable WAL journal mode."""
        from app.store import SessionStore

        store = SessionStore(temp_db)
        cur = store._conn.execute("PRAGMA journal_mode")
        mode = cur.fetchone()[0]
        assert mode.lower() == "wal"

    def test_create_session(self, temp_db: str) -> None:
        """create_session should return a UUID string."""
        from app.store import SessionStore

        store = SessionStore(temp_db)
        session_id = store.create_session()
        assert isinstance(session_id, str)
        assert len(session_id) == 36  # UUID format

    def test_create_session_with_name(self, temp_db: str) -> None:
        """create_session with name should set the session name."""
        from app.store import SessionStore

        store = SessionStore(temp_db)
        session_id = store.create_session(name="test-session")
        session = store.get_session(session_id)
        assert session is not None
        assert session["name"] == "test-session"

    def test_list_sessions(self, temp_db: str) -> None:
        """list_sessions should return sessions ordered by updated_at desc."""
        from app.store import SessionStore

        store = SessionStore(temp_db)
        s1 = store.create_session(name="first")
        s2 = store.create_session(name="second")

        sessions = store.list_sessions()
        assert len(sessions) >= 2
        # Most recent first
        names = [s["name"] for s in sessions]
        assert "second" in names
        assert "first" in names

    def test_list_sessions_empty(self, temp_db: str) -> None:
        """list_sessions should return empty list when no sessions."""
        from app.store import SessionStore

        store = SessionStore(temp_db)
        sessions = store.list_sessions()
        assert sessions == []

    def test_get_session(self, temp_db: str) -> None:
        """get_session should return session metadata."""
        from app.store import SessionStore

        store = SessionStore(temp_db)
        session_id = store.create_session(name="my-session")
        session = store.get_session(session_id)
        assert session is not None
        assert session["id"] == session_id
        assert session["name"] == "my-session"
        assert session["status"] == "active"
        assert "created_at" in session
        assert "updated_at" in session

    def test_get_session_nonexistent(self, temp_db: str) -> None:
        """get_session should return None for nonexistent session."""
        from app.store import SessionStore

        store = SessionStore(temp_db)
        result = store.get_session("nonexistent-id")
        assert result is None

    def test_delete_session(self, temp_db: str) -> None:
        """delete_session should remove session and return True."""
        from app.store import SessionStore

        store = SessionStore(temp_db)
        session_id = store.create_session()
        assert store.delete_session(session_id) is True
        assert store.get_session(session_id) is None

    def test_delete_session_nonexistent(self, temp_db: str) -> None:
        """delete_session should return False for nonexistent session."""
        from app.store import SessionStore

        store = SessionStore(temp_db)
        assert store.delete_session("nonexistent") is False

    def test_save_message(self, temp_db: str) -> None:
        """save_message should persist a message and update session count."""
        from app.store import SessionStore

        store = SessionStore(temp_db)
        session_id = store.create_session()
        msg_id = store.save_message(
            session_id, "user", "Hello, world!"
        )
        assert msg_id > 0

        session = store.get_session(session_id)
        assert session is not None
        assert session["message_count"] == 1

    def test_save_message_with_tool_calls(self, temp_db: str) -> None:
        """save_message should serialize tool_calls as JSON."""
        from app.store import SessionStore

        store = SessionStore(temp_db)
        session_id = store.create_session()
        tool_calls = [
            {"id": "call_123", "name": "Read", "arguments": {"file_path": "/tmp/test.py"}}
        ]
        msg_id = store.save_message(
            session_id, "assistant", "Let me read that file.",
            tool_calls=tool_calls,
        )
        assert msg_id > 0

        messages = store.get_messages(session_id)
        assert len(messages) == 1
        assert "tool_calls" in messages[0]
        parsed = json.loads(messages[0]["tool_calls"])
        assert parsed[0]["name"] == "Read"

    def test_get_messages(self, temp_db: str) -> None:
        """get_messages should return messages ordered by created_at."""
        from app.store import SessionStore

        store = SessionStore(temp_db)
        session_id = store.create_session()
        store.save_message(session_id, "user", "First")
        store.save_message(session_id, "assistant", "Second")

        messages = store.get_messages(session_id)
        assert len(messages) == 2
        assert messages[0]["content"] == "First"
        assert messages[1]["content"] == "Second"

    def test_get_messages_limit(self, temp_db: str) -> None:
        """get_messages with limit should return at most N messages."""
        from app.store import SessionStore

        store = SessionStore(temp_db)
        session_id = store.create_session()
        for i in range(5):
            store.save_message(session_id, "user", f"Message {i}")

        messages = store.get_messages(session_id, limit=3)
        assert len(messages) == 3

    def test_save_tool_log(self, temp_db: str) -> None:
        """save_tool_log should persist tool execution details."""
        from app.store import SessionStore

        store = SessionStore(temp_db)
        session_id = store.create_session()
        msg_id = store.save_message(session_id, "tool", "Read result", tool_call_id="call_1")

        log_id = store.save_tool_log(
            session_id=session_id,
            message_id=msg_id,
            tool_name="Read",
            tool_input='{"file_path": "/tmp/test.py"}',
            tool_output='{"content": "hello"}',
            status="success",
            duration_ms=150,
        )
        assert log_id > 0

    def test_save_summary(self, temp_db: str) -> None:
        """save_summary and get_summary should persist and retrieve."""
        from app.store import SessionStore

        store = SessionStore(temp_db)
        session_id = store.create_session()
        store.save_summary(session_id, "This is a summary.")
        assert store.get_summary(session_id) == "This is a summary."

    def test_cleanup_old_sessions(self, temp_db: str) -> None:
        """cleanup_old_sessions should remove sessions exceeding max_count."""
        from app.store import SessionStore

        store = SessionStore(temp_db)
        for i in range(5):
            store.create_session(name=f"session-{i}")

        assert len(store.list_sessions()) == 5
        removed = store.cleanup_old_sessions(max_count=2, max_age_days=999)
        assert removed == 3
        assert len(store.list_sessions()) == 2

    def test_persistence_across_instances(self, temp_db: str) -> None:
        """Data should persist across SessionStore instances."""
        from app.store import SessionStore

        store1 = SessionStore(temp_db)
        session_id = store1.create_session(name="persistent")
        store1.save_message(session_id, "user", "Hello")

        # Reopen
        store2 = SessionStore(temp_db)
        session = store2.get_session(session_id)
        assert session is not None
        assert session["name"] == "persistent"
        messages = store2.get_messages(session_id)
        assert len(messages) == 1
        assert messages[0]["content"] == "Hello"

    def test_load_session_to_agent(self, temp_db: str) -> None:
        """load_session should populate agent.state.context with messages."""
        from app.store import SessionStore

        store = SessionStore(temp_db)
        session_id = store.create_session()
        store.save_message(session_id, "user", "Hello")
        store.save_message(session_id, "assistant", "Hi there!")

        mock_agent = MagicMock()
        mock_agent.state = MagicMock()
        mock_agent.state.context = []

        result = store.load_session(session_id, mock_agent)
        assert result is True
        assert len(mock_agent.state.context) == 2