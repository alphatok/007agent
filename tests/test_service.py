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


class TestRouteOrdering:
    """Test that static routes are registered before parameterized ones."""

    def test_pending_questions_before_task_id(self):
        """Verify /api/tasks/pending-questions is registered before /api/tasks/{task_id}.

        This prevents FastAPI from matching 'pending-questions' as a task_id.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        routes_registered = []

        # Simulate the ORDER that routes should be registered
        @app.get("/api/tasks/pending-questions")
        async def pending_questions():
            routes_registered.append("pending-questions")
            return {}

        @app.get("/api/tasks/{task_id}")
        async def get_task(task_id: str):
            routes_registered.append(f"task_id={task_id}")
            return {"task_id": task_id}

        client = TestClient(app)
        resp = client.get("/api/tasks/pending-questions")
        assert resp.status_code == 200
        # Should match pending-questions, not task_id
        assert routes_registered == ["pending-questions"]
        assert routes_registered[0] != "task_id=pending-questions"

    def test_real_app_pending_questions_route(self):
        """Verify the real app registers pending-questions before task_id routes."""
        # Check that pending-questions route exists and works
        from fastapi.testclient import TestClient
        from unittest.mock import MagicMock, patch

        with patch("app.tools.get_pending_questions", return_value={}):
            # Build a minimal app with the route
            from app.service import create_app

            mock_agent = MagicMock()
            mock_agent.name = "test"
            mock_agent.state = MagicMock()
            mock_agent.state.summary = None

            app = create_app(mock_agent)

            routes = [r.path for r in app.routes if hasattr(r, "path")]
            pending_idx = routes.index("/api/tasks/pending-questions")
            task_id_idx = routes.index("/api/tasks/{task_id}")

            assert pending_idx < task_id_idx, (
                f"/api/tasks/pending-questions (index {pending_idx}) must be "
                f"before /api/tasks/{{task_id}} (index {task_id_idx})"
            )


class TestChatPageJsSyntax:
    """Test that the generated JS in CHAT_PAGE is syntactically valid."""

    def test_js_syntax_valid(self):
        """Verify the embedded JavaScript has no syntax errors."""
        import subprocess
        import tempfile
        import os
        import re

        from app.service import CHAT_PAGE

        m = re.search(r"<script>(.*?)</script>", CHAT_PAGE, re.DOTALL)
        assert m is not None, "No <script> tag found in CHAT_PAGE"
        js = m.group(1)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False,
        ) as f:
            f.write(js)
            tmp_path = f.name

        try:
            result = subprocess.run(
                ["node", "--check", tmp_path],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, (
                f"JS syntax error in CHAT_PAGE:\n{result.stderr}"
            )
        finally:
            os.unlink(tmp_path)

    def test_js_no_unescaped_single_quotes_in_strings(self):
        """Verify Python string escaping doesn't break JS single-quoted strings.

        Regression: \\' in Python \"\"\"...\"\"\" becomes just ' in output,
        which can break JS single-quoted strings like toggle('expanded').
        """
        import re

        from app.service import CHAT_PAGE

        m = re.search(r"<script>(.*?)</script>", CHAT_PAGE, re.DOTALL)
        js = m.group(1)

        # Check that toggle('expanded') appears correctly
        assert "toggle(\\'expanded\\')" in js, (
            "toggle needs escaped quotes: toggle(\\'expanded\\')"
        )


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
