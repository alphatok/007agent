"""Cross-session memory with CRUD and lifecycle management.

Memory is stored in SQLite (metadata) with zvec for vector + FTS search.
Three memory types: episodic, semantic, procedural.
Two scopes: 'global' (cross-session) | 'session' (session-scoped).

Lifecycle: extract -> consolidate (episodic -> semantic) -> decay (cleanup).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


def _now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    """Cross-session memory store backed by SQLite + zvec.

    Usage::

        store = MemoryStore("data/agent.db", "data/zvec")
        store.add_memory("semantic", "用户偏好使用 uv 管理 Python 依赖")
        store.extract_from_session("session-1", messages)
    """

    def __init__(self, db_path: str, zvec_path: str) -> None:
        self._db_path = db_path
        self._zvec_path = zvec_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._create_tables()
        self._zvec_collection = None
        self._init_zvec()

    def _create_tables(self) -> None:
        """Create memories table if it doesn't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'global',
                source_session_id TEXT,
                metadata TEXT,
                importance REAL DEFAULT 0.5,
                access_count INTEGER DEFAULT 0,
                last_accessed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_memories_type
                ON memories(type, created_at);
            CREATE INDEX IF NOT EXISTS idx_memories_importance
                ON memories(importance DESC);
            CREATE INDEX IF NOT EXISTS idx_memories_accessed
                ON memories(last_accessed_at);
            CREATE INDEX IF NOT EXISTS idx_memories_scope
                ON memories(scope, created_at);
        """)
        self._conn.commit()
        self._migrate_add_scope()

    def _migrate_add_scope(self) -> None:
        """Add scope column for existing databases (migration)."""
        try:
            self._conn.execute(
                "ALTER TABLE memories ADD COLUMN scope TEXT NOT NULL DEFAULT 'global'"
            )
            self._conn.commit()
            logger.info("[Memory] Migration: added scope column")
        except sqlite3.OperationalError:
            pass  # Column already exists

    def _init_zvec(self) -> None:
        """Initialize zvec collection for vector + FTS."""
        try:
            import zvec

            schema = zvec.CollectionSchema(
                name="memories",
                vectors=[
                    zvec.VectorSchema(
                        "embedding", zvec.DataType.VECTOR_FP32, 384,
                    ),
                ],
            )
            self._zvec_collection = zvec.create_and_open(
                path=self._zvec_path,
                schema=schema,
            )
            # Create FTS index on content field
            try:
                self._zvec_collection.create_index(
                    field_name="content",
                    index_type=zvec.IndexType.Invert,
                    index_option=zvec.IndexOption(
                        fts=zvec.FtsIndexParam(),
                    ),
                )
            except Exception:
                pass  # Index may already exist
        except Exception:
            self._zvec_collection = None

    # ---- Memory CRUD ----

    def add_memory(self, type: str, content: str,
                   source_session_id: str | None = None,
                   metadata: dict | None = None,
                   importance: float = 0.5,
                   scope: str = "global") -> str:
        """Add a memory entry. Deduplicates by content. Returns memory_id.

        Args:
            type: Memory type: episodic | semantic | procedural.
            content: Memory content.
            source_session_id: Session that created this memory.
            metadata: Optional JSON metadata.
            importance: Importance score 0.0-1.0.
            scope: 'global' (cross-session) or 'session' (session-scoped).
        """
        # Dedup: check for exact content match
        existing = self._conn.execute(
            "SELECT id, importance, access_count FROM memories WHERE content = ?",
            (content,),
        ).fetchone()
        if existing:
            # Merge: update importance (take max) and bump access_count
            new_importance = max(existing["importance"], importance)
            self._conn.execute(
                """UPDATE memories
                   SET importance = ?, access_count = access_count + 1,
                       updated_at = ?
                   WHERE id = ?""",
                (new_importance, _now(), existing["id"]),
            )
            self._conn.commit()
            logger.info(
                "[Memory] Merged duplicate: '%s...' (id: %s, importance: %.1f)",
                content[:50], existing["id"][:8], new_importance,
            )
            return existing["id"]

        memory_id = str(uuid.uuid4())
        now = _now()
        self._conn.execute(
            """INSERT INTO memories
               (id, type, content, scope, source_session_id, metadata,
                importance, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (memory_id, type, content, scope, source_session_id,
             json.dumps(metadata or {}, ensure_ascii=False),
             importance, now, now),
        )
        self._conn.commit()
        logger.info(
            "[Memory] Added %s (scope=%s): '%s...' (id: %s, importance: %.1f)",
            type, scope, content[:50], memory_id[:8], importance,
        )
        return memory_id

    def get_memory(self, memory_id: str) -> dict | None:
        """Get a memory by ID. Updates access_count."""
        row = self._conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if row is None:
            return None
        # Update access stats
        self._conn.execute(
            """UPDATE memories
               SET access_count = access_count + 1,
                   last_accessed_at = ?
               WHERE id = ?""",
            (_now(), memory_id),
        )
        self._conn.commit()
        return dict(row)

    def update_memory(self, memory_id: str, **kwargs) -> bool:
        """Update memory fields. Returns True if updated."""
        mem = self._conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if mem is None:
            logger.warning(
                "[Memory] Update failed: memory not found (id: %s)",
                memory_id[:8],
            )
            return False

        allowed = {"type", "content", "source_session_id",
                   "metadata", "importance", "scope"}
        updates = {}
        for key, value in kwargs.items():
            if key in allowed:
                updates[key] = (
                    json.dumps(value, ensure_ascii=False)
                    if key == "metadata" else value
                )

        if not updates:
            return False

        set_clause = ", ".join(
            f"{k} = ?" for k in updates
        )
        set_clause += ", updated_at = ?"
        values = list(updates.values()) + [_now(), memory_id]
        self._conn.execute(
            f"UPDATE memories SET {set_clause} WHERE id = ?",
            values,
        )
        self._conn.commit()
        logger.info(
            "[Memory] Updated (id: %s, fields: %s)",
            memory_id[:8], ", ".join(updates.keys()),
        )
        return True

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory from SQLite."""
        mem = self._conn.execute(
            "SELECT id, content FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if mem is None:
            logger.warning(
                "[Memory] Delete failed: memory not found (id: %s)",
                memory_id[:8],
            )
            return False
        self._conn.execute(
            "DELETE FROM memories WHERE id = ?", (memory_id,)
        )
        self._conn.commit()
        logger.info(
            "[Memory] Deleted (id: %s, content: '%s...')",
            memory_id[:8], mem["content"][:50],
        )
        return True

    def list_memories(self, type: str | None = None,
                      scope: str | None = None,
                      limit: int = 50) -> list[dict]:
        """List memories, optionally filtered by type and/or scope.

        Args:
            type: Filter by memory type (episodic | semantic | procedural).
            scope: Filter by scope ('global' | 'session') or None for all.
            limit: Maximum results.
        """
        conditions = []
        params = []
        if type:
            conditions.append("type = ?")
            params.append(type)
        if scope:
            conditions.append("scope = ?")
            params.append(scope)

        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)
        rows = self._conn.execute(
            f"""SELECT * FROM memories
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT ?""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- Memory Lifecycle ----

    def extract_from_session(self, session_id: str,
                             messages: list[dict]) -> list[str]:
        """Extract memories from session messages using LLM.

        Args:
            session_id: Source session ID.
            messages: List of {"role": str, "content": str} dicts.

        Returns:
            List of created memory IDs.
        """
        items = self._extract_with_llm(session_id, messages)
        ids = []
        for mem_type, content in items:
            mem_id = self.add_memory(
                type=mem_type,
                content=content,
                source_session_id=session_id,
            )
            ids.append(mem_id)
        return ids

    def _extract_with_llm(self, session_id: str,
                          messages: list[dict]) -> list[tuple[str, str]]:
        """Call LLM to extract memory items from messages.

        Override or mock this method for testing.
        Returns list of (type, content) tuples.
        """
        # Default: no-op, return empty
        return []

    def consolidate(self, threshold: int = 3) -> int:
        """Consolidate: upgrade high-access episodic memories to semantic.

        Returns count of consolidated memories.
        """
        rows = self._conn.execute(
            """SELECT id FROM memories
               WHERE type = 'episodic'
               AND access_count >= ?""",
            (threshold,),
        ).fetchall()
        count = 0
        for row in rows:
            self._conn.execute(
                """UPDATE memories
                   SET type = 'semantic', updated_at = ?
                   WHERE id = ?""",
                (_now(), row["id"]),
            )
            count += 1
        self._conn.commit()
        return count

    def decay(self, max_age_days: int = 30,
              importance_threshold: float = 0.3) -> int:
        """Decay: remove low-importance, old memories.

        Returns count of deleted memories.
        """
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) -
                  timedelta(days=max_age_days)).isoformat()

        rows = self._conn.execute(
            """SELECT id FROM memories
               WHERE importance < ?
               AND (last_accessed_at IS NULL
                    OR last_accessed_at < ?)""",
            (importance_threshold, cutoff),
        ).fetchall()
        count = 0
        for row in rows:
            self._conn.execute(
                "DELETE FROM memories WHERE id = ?", (row["id"],)
            )
            count += 1
        self._conn.commit()
        return count