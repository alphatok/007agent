"""Skill system - auto-discover and load skills from the skills directory.

A skill is a Python module that exports a `get_tools()` function returning
a list of AgentScope Tool instances.

To add a new skill:
  1. Create a new .py file in this directory
  2. Define a `get_tools() -> list` function
  3. The skill will be auto-discovered on next startup
"""
import importlib
import importlib.util
from pathlib import Path
from typing import Any


def discover_skills() -> list[Any]:
    """Discover and load all skills from the skills directory.

    Scans for *.py files (excluding __init__.py and _private.py),
    imports each module, and calls its get_tools() function.

    Returns:
        Combined list of tools from all discovered skills.
    """
    skills_dir = Path(__file__).parent
    tools: list[Any] = []

    for file in sorted(skills_dir.glob("*.py")):
        if file.name.startswith("_") or file.name == "__init__.py":
            continue

        module_name = f"skills.{file.stem}"
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, "get_tools"):
                skill_tools = module.get_tools()
                tools.extend(skill_tools)
        except Exception:
            # Skill failed to load, skip it
            pass

    return tools