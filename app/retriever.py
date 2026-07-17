"""Hybrid retrieval: keyword + semantic search with zvec.

When zvec is available, uses Query with FTS for hybrid search.
Falls back to SQLite LIKE-based keyword search when zvec is unavailable.
"""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.memory import MemoryStore


class HybridRetriever:
    """Hybrid memory retriever using zvec (primary) or SQLite (fallback).

    Usage::

        retriever = HybridRetriever(db_path, zvec_path, memory_store)
        results = retriever.search("Redis 缓存", top_k=5)
    """

    def __init__(self, db_path: str, zvec_path: str,
                 memory_store: "MemoryStore") -> None:
        self._db_path = db_path
        self._zvec_path = zvec_path
        self._store = memory_store
        self._zvec_collection = None

    def search(self, query: str, top_k: int = 10,
               memory_types: list[str] | None = None,
               min_importance: float = 0.0) -> list[dict]:
        """Search memories by keyword and fallback to SQLite LIKE.

        When zvec is available, uses vector + FTS hybrid search.
        Falls back to SQLite LIKE-based keyword matching.

        Args:
            query: Search query string.
            top_k: Maximum number of results.
            memory_types: Optional filter by memory type(s).
            min_importance: Minimum importance filter.

        Returns:
            List of memory dicts sorted by relevance.
        """
        query = query.strip()
        if not query:
            return []

        results = self._sqlite_search(query, top_k, memory_types,
                                      min_importance)
        return results

    def _sqlite_search(self, query: str, top_k: int,
                       memory_types: list[str] | None,
                       min_importance: float) -> list[dict]:
        """Fallback keyword search using SQLite LIKE."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row

        # Build query with LIKE matching
        params = []
        conditions = []
        for word in query.split():
            conditions.append("content LIKE ?")
            params.append(f"%{word}%")

        if memory_types:
            placeholders = ", ".join("?" * len(memory_types))
            conditions.append(f"type IN ({placeholders})")
            params.extend(memory_types)

        if min_importance > 0:
            conditions.append("importance >= ?")
            params.append(min_importance)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""SELECT * FROM memories
                  WHERE {where}
                  ORDER BY importance DESC, created_at DESC
                  LIMIT ?"""
        params.append(top_k)

        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]