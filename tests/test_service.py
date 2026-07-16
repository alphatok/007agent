"""Tests for app.service module."""
import pytest


class TestService:
    """Tests for Agent Service entry point."""

    def test_service_module_exists(self) -> None:
        """Service module should be importable."""
        from app import service
        assert service is not None

    def test_create_app_returns_fastapi(self) -> None:
        """create_app should return a FastAPI instance."""
        from unittest.mock import MagicMock

        from app.service import create_app

        mock_agent = MagicMock()
        app = create_app(mock_agent)
        assert app is not None
        # FastAPI app should have routes
        assert len(app.routes) > 0