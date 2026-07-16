"""Centralized configuration loaded from environment variables."""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Typed application configuration.

    All values are loaded from environment variables with sensible defaults.
    """

    deepseek_api_key: str
    """DeepSeek API key (required)."""

    deepseek_model: str = "deepseek-v4-pro"
    """Model name to use for DeepSeek API."""

    deepseek_base_url: str = "https://api.deepseek.com"
    """Base URL for DeepSeek API."""

    permission_mode: str = "bypass"
    """Permission mode: bypass, ask, or deny."""

    chrome_mcp_enabled: bool = True
    """Whether to enable Chrome DevTools MCP integration."""


def load_config() -> Config:
    """Load configuration from environment variables.

    Returns:
        Config instance with values from environment or defaults.
    """
    return Config(
        deepseek_api_key=os.environ["DEEPSEEK_API_KEY"],
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        deepseek_base_url=os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        ),
        permission_mode=os.getenv("PERMISSION_MODE", "bypass"),
        chrome_mcp_enabled=os.getenv("CHROME_MCP_ENABLED", "true").lower()
        == "true",
    )