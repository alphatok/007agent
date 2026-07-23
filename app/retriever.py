"""Hybrid retrieval: keyword + semantic search with zvec.

When zvec is available, uses MultiQuery (VectorQuery + FTSQuery) for hybrid
search. Falls back to SQLite LIKE-based keyword search when zvec or embedding
is unavailable.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

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
        self._embedding_provider = None
        self._init_zvec()

    def _init_zvec(self) -> None:
        """Try to open zvec collection and initialize embedding provider."""
        try:
            import zvec

            self._zvec_collection = zvec.open(
                path=self._zvec_path,
            )
        except Exception:
            self._zvec_collection = None
            return

        # Try to initialize embedding provider for vector search
        try:
            from app.embedding import EmbeddingProvider
            from app.config import load_config

            config = load_config()
            self._embedding_provider = EmbeddingProvider(
                backend=config.embedding_backend,
                model_name=config.embedding_model_name,
            )
        except Exception:
            self._embedding_provider = None

    def search(self, query: str, top_k: int = 10,
               memory_types: list[str] | None = None,
               min_importance: float = 0.0,
               scope: str | None = None) -> list[dict]:
        """Search memories with zvec hybrid search (vector + FTS).

        Falls back to SQLite LIKE when zvec or embedding is unavailable.

        Args:
            query: Search query string.
            top_k: Maximum number of results.
            memory_types: Optional filter by memory type(s).
            min_importance: Minimum importance filter.
            scope: Optional filter by scope ('global' | 'session').

        Returns:
            List of memory dicts sorted by relevance.
        """
        query = query.strip()
        if not query:
            return []

        # Try zvec vector + FTS hybrid search first
        if self._zvec_collection is not None and self._embedding_provider is not None:
            try:
                return self._zvec_search(query, top_k, memory_types,
                                         min_importance, scope)
            except Exception as e:
                logger.debug(
                    "[Retriever] zvec search failed, falling back to SQLite: %s", e,
                )

        # Fallback: SQLite LIKE keyword search
        return self._sqlite_search(query, top_k, memory_types,
                                   min_importance, scope)

    def _zvec_search(self, query: str, top_k: int,
                     memory_types: list[str] | None,
                     min_importance: float,
                     scope: str | None = None) -> list[dict]:
        """Hybrid search using zvec MultiQuery (vector + FTS)."""
        import zvec

        # Generate embedding for the query
        embedding = self._embedding_provider.embed(query)  # type: ignore[union-attr]
        if not embedding:
            return []

        # Build queries
        queries = [
            zvec.VectorQuery("embedding", vector=embedding, topk=top_k * 2),
            zvec.FTSQuery("content", query=query, topk=top_k * 2),
        ]

        # Build filter expression
        filter_parts = []
        if memory_types:
            type_conditions = " OR ".join(
                f'type == "{t}"' for t in memory_types
            )
            filter_parts.append(f"({type_conditions})")
        if min_importance > 0:
            filter_parts.append(f"importance >= {min_importance}")
        if scope:
            filter_parts.append(f'scope == "{scope}"')

        filter_expr = " AND ".join(filter_parts) if filter_parts else None

        result = self._zvec_collection.search(  # type: ignore[union-attr]
            zvec.MultiQuery(*queries, filter_expr=filter_expr),
            limit=top_k,
        )

        # Map zvec results to memory dicts
        memory_ids = [r.doc_id for r in result]
        memories = []
        if memory_ids:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            placeholders = ", ".join("?" * len(memory_ids))
            rows = conn.execute(
                f"SELECT * FROM memories WHERE id IN ({placeholders})",
                memory_ids,
            ).fetchall()
            conn.close()
            # Preserve zvec result order
            row_map = {r["id"]: dict(r) for r in rows}
            memories = [row_map[mid] for mid in memory_ids if mid in row_map]

        return memories

    def _sqlite_search(self, query: str, top_k: int,
                       memory_types: list[str] | None,
                       min_importance: float,
                       scope: str | None = None) -> list[dict]:
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

        if scope:
            conditions.append("scope = ?")
            params.append(scope)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""SELECT * FROM memories
                  WHERE {where}
                  ORDER BY importance DESC, created_at DESC
                  LIMIT ?"""
        params.append(top_k)

        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]