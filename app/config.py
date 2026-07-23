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

    compaction_trigger_ratio: float = 0.4
    """Context compaction trigger ratio (0.4 = 40% of 128K = 51.2K tokens)."""

    compaction_warning_tokens: int = 20000
    """Token threshold for context warning level."""

    # ---- Persistence ----
    data_dir: str = "data"
    """Data directory for all persistent storage."""

    db_path: str = "data/agent.db"
    """SQLite database path."""

    zvec_path: str = "data/zvec"
    """zvec vector database path."""

    session_max_count: int = 50
    """Maximum number of sessions to retain."""

    session_max_age_days: int = 30
    """Maximum age of sessions in days before cleanup."""

    persistence_mode: str = "save-all"
    """Persistence mode: save-all | chat-only | none."""

    # ---- Memory ----
    memory_enabled: bool = True
    """Whether memory system is enabled."""

    memory_extraction_enabled: bool = True
    """Whether to auto-extract memories during compaction."""

    memory_consolidation_threshold: int = 3
    """Access count threshold for episodic -> semantic consolidation."""

    memory_decay_days: int = 30
    """Days before low-importance memories are decayed."""

    # ---- Embedding ----
    embedding_backend: str = "fastembed"
    """Embedding backend: fastembed | deepseek."""

    embedding_model_name: str = "BAAI/bge-small-zh-v1.5"
    """FastEmbed model name (only used when embedding_backend=fastembed)."""

    # ---- Tool Retry ----
    tool_retry_max: int = 3
    """Maximum number of retries for tool calls."""

    tool_retry_backoff: float = 2.0
    """Backoff multiplier for tool retry delays."""

    tool_retry_initial_delay: float = 1.0
    """Initial delay in seconds before first tool retry."""

    # ---- Workspace ----
    workspace_root: str = "workspace"
    """Workspace root directory for file operations. Relative to project root."""


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
        compaction_trigger_ratio=float(
            os.getenv("COMPACTION_TRIGGER_RATIO", "0.4"),
        ),
        compaction_warning_tokens=int(
            os.getenv("COMPACTION_WARNING_TOKENS", "20000"),
        ),
        data_dir=os.getenv("DATA_DIR", "data"),
        db_path=os.getenv("DB_PATH", "data/agent.db"),
        zvec_path=os.getenv("ZVEC_PATH", "data/zvec"),
        session_max_count=int(
            os.getenv("SESSION_MAX_COUNT", "50"),
        ),
        session_max_age_days=int(
            os.getenv("SESSION_MAX_AGE_DAYS", "30"),
        ),
        persistence_mode=os.getenv("PERSISTENCE_MODE", "save-all"),
        memory_enabled=os.getenv("MEMORY_ENABLED", "true").lower() == "true",
        memory_extraction_enabled=os.getenv(
            "MEMORY_EXTRACTION_ENABLED", "true"
        ).lower()
        == "true",
        memory_consolidation_threshold=int(
            os.getenv("MEMORY_CONSOLIDATION_THRESHOLD", "3"),
        ),
        memory_decay_days=int(
            os.getenv("MEMORY_DECAY_DAYS", "30"),
        ),
        embedding_backend=os.getenv("EMBEDDING_BACKEND", "fastembed"),
        embedding_model_name=os.getenv(
            "EMBEDDING_MODEL_NAME", "BAAI/bge-small-zh-v1.5"
        ),
        tool_retry_max=int(os.getenv("TOOL_RETRY_MAX", "3")),
        tool_retry_backoff=float(
            os.getenv("TOOL_RETRY_BACKOFF", "2.0"),
        ),
        tool_retry_initial_delay=float(
            os.getenv("TOOL_RETRY_INITIAL_DELAY", "1.0"),
        ),
        workspace_root=os.getenv("WORKSPACE_ROOT", "workspace"),
    )