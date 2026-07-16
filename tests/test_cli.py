"""Tests for app.cli module."""
import pytest


class TestCli:
    """Tests for CLI entry point."""

    def test_cli_module_exists(self) -> None:
        """CLI module should be importable."""
        from app import cli
        assert cli is not None

    def test_run_cli_is_async_function(self) -> None:
        """run_cli should be an async function."""
        import inspect
        from app.cli import run_cli

        assert inspect.iscoroutinefunction(run_cli)