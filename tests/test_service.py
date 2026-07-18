"""Tests for service endpoints - session continuity."""
import importlib
import pytest
import sys
import tempfile
import os
from pathlib import Path

# Ensure app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.service import _read_active_session, _write_active_session


class TestActiveSessionFile:
    """Test active_session.txt file helpers."""

    def test_read_no_file(self):
        """Test reading when file doesn't exist."""
        with tempfile.TemporaryDirectory() as d:
            result = _read_active_session(d)
            assert result is None

    def test_write_read_roundtrip(self):
        """Test write then read returns same session_id."""
        with tempfile.TemporaryDirectory() as d:
            _write_active_session(d, "test-session-123")
            result = _read_active_session(d)
            assert result == "test-session-123"

    def test_read_empty_file(self):
        """Test reading an empty file returns None."""
        with tempfile.TemporaryDirectory() as d:
            active_file = os.path.join(d, "active_session.txt")
            with open(active_file, "w") as f:
                f.write("")
            result = _read_active_session(d)
            assert result is None


class TestSessionStore:
    """Test store-level session persistence."""

    def test_load_session_with_limit(self):
        """Test load_session with limit parameter."""
        import app.store
        importlib.reload(app.store)
        from app.store import SessionStore

        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            store = SessionStore(f.name)
            sid = store.create_session()
            for i in range(10):
                store.save_message(sid, "user", f"Message {i}")

            # Create a mock agent
            class MockAgent:
                class State:
                    context = []
                state = State()

            agent = MockAgent()
            store.load_session(sid, agent, limit=3)
            assert len(agent.state.context) == 3

    def test_get_first_user_message(self):
        """Test getting first user message for session naming."""
        import app.store
        importlib.reload(app.store)
        from app.store import SessionStore

        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            store = SessionStore(f.name)
            sid = store.create_session()
            store.save_message(sid, "user", "Hello, this is my first message")
            store.save_message(sid, "assistant", "Hi there!")
            store.save_message(sid, "user", "Second message")

            first = store.get_first_user_message(sid)
            assert first == "Hello, this is my first message"

    def test_get_first_user_message_no_messages(self):
        """Test getting first user message when no exist."""
        import app.store
        importlib.reload(app.store)
        from app.store import SessionStore

        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            store = SessionStore(f.name)
            sid = store.create_session()
            assert store.get_first_user_message(sid) is None
