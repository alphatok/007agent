"""Memory tools for Agent — search, add, list, update, forget memories.

These are registered as FunctionTools so the Agent can call them
directly to manage its cross-session memory.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from agentscope.message import TextBlock, ToolResultState
from agentscope.tool import FunctionTool, ToolChunk

if TYPE_CHECKING:
    from app.memory import MemoryStore
    from app.retriever import HybridRetriever


_store: "MemoryStore | None" = None
_retriever: "HybridRetriever | None" = None
_current_session_id: str | None = None


def set_memory_store(store: "MemoryStore") -> None:
    """Set the global memory store for tool access."""
    global _store
    _store = store


def set_retriever(retriever: "HybridRetriever") -> None:
    """Set the global retriever for tool access."""
    global _retriever
    _retriever = retriever


def set_current_session_id(session_id: str | None) -> None:
    """Set the current session ID for session-scoped memories."""
    global _current_session_id
    _current_session_id = session_id


async def _search_memory(query: str, memory_type: str = "all",
                         top_k: int = 5,
                         scope: str = "all") -> ToolChunk:
    """Search memories using hybrid retrieval (keyword + semantic).

    Args:
        query: Search query string.
        memory_type: Filter by type: episodic | semantic | procedural | all.
        top_k: Maximum number of results.
        scope: Filter by scope: global | session | all.
    """
    yield ToolChunk(
        content=[TextBlock(text=f"[Tool] Searching memory: '{query}' (scope={scope})...")],
        state=ToolResultState.RUNNING,
    )

    if _store is None:
        yield ToolChunk(
            content=[TextBlock(
                text="[FAIL] Memory store not initialized"
            )],
            state=ToolResultState.ERROR,
        )
        return

    if _retriever is None:
        yield ToolChunk(
            content=[TextBlock(
                text="[FAIL] Retriever not initialized"
            )],
            state=ToolResultState.ERROR,
        )
        return

    types = None if memory_type == "all" else [memory_type]
    scope_filter = None if scope == "all" else scope
    results = _retriever.search(
        query, top_k=top_k, memory_types=types, scope=scope_filter,
    )

    if not results:
        yield ToolChunk(
            content=[TextBlock(text="[Tool] No matching memories found.")],
            state=ToolResultState.SUCCESS,
        )
        return

    output_lines = [f"[ OK ] Found {len(results)} memories:"]
    for i, mem in enumerate(results):
        output_lines.append(
            f"  [{mem['type']}] {mem['content']} "
            f"(importance: {mem.get('importance', 0):.1f}, "
            f"id: {mem['id'][:8]}...)"
        )

    yield ToolChunk(
        content=[TextBlock(text="\n".join(output_lines))],
        state=ToolResultState.SUCCESS,
    )


async def _add_memory(content: str, type: str = "semantic",
                      importance: float = 0.5,
                      scope: str = "global") -> ToolChunk:
    """Add a memory to the store.

    Args:
        content: Memory content.
        type: Memory type: episodic | semantic | procedural.
        importance: Importance score 0.0-1.0.
        scope: 'global' (cross-session) or 'session' (current session only).
    """
    yield ToolChunk(
        content=[TextBlock(
            text=f"[Tool] Adding {type} memory (scope={scope}): '{content[:50]}...'"
        )],
        state=ToolResultState.RUNNING,
    )

    if _store is None:
        yield ToolChunk(
            content=[TextBlock(
                text="[FAIL] Memory store not initialized"
            )],
            state=ToolResultState.ERROR,
        )
        return

    memory_id = _store.add_memory(
        type=type, content=content, importance=importance,
        scope=scope, source_session_id=_current_session_id,
    )

    yield ToolChunk(
        content=[TextBlock(
            text=f"[ OK ] Memory added (id: {memory_id[:8]}...) "
                 f"type={type}, scope={scope}, importance={importance}"
        )],
        state=ToolResultState.SUCCESS,
    )


async def _list_memories(memory_type: str = "all",
                         scope: str = "all",
                         limit: int = 20) -> ToolChunk:
    """List memories from the store.

    Args:
        memory_type: Filter by type: episodic | semantic | procedural | all.
        scope: Filter by scope: global | session | all.
        limit: Maximum number of results.
    """
    yield ToolChunk(
        content=[TextBlock(text="[Tool] Listing memories...")],
        state=ToolResultState.RUNNING,
    )

    if _store is None:
        yield ToolChunk(
            content=[TextBlock(
                text="[FAIL] Memory store not initialized"
            )],
            state=ToolResultState.ERROR,
        )
        return

    memories = _store.list_memories(
        type=None if memory_type == "all" else memory_type,
        scope=None if scope == "all" else scope,
        limit=limit,
    )

    if not memories:
        yield ToolChunk(
            content=[TextBlock(text="[ OK ] No memories found.")],
            state=ToolResultState.SUCCESS,
        )
        return

    output_lines = [f"[ OK ] {len(memories)} memories:"]
    for mem in memories:
        output_lines.append(
            f"  [{mem['type']}] {mem['content']} "
            f"(importance: {mem.get('importance', 0):.1f}, "
            f"id: {mem['id'][:8]}...)"
        )

    yield ToolChunk(
        content=[TextBlock(text="\n".join(output_lines))],
        state=ToolResultState.SUCCESS,
    )


async def _forget_memory(memory_id: str) -> ToolChunk:
    """Delete a memory by ID.

    Args:
        memory_id: ID of the memory to delete.
    """
    yield ToolChunk(
        content=[TextBlock(
            text=f"[Tool] Forgetting memory: {memory_id[:8]}..."
        )],
        state=ToolResultState.RUNNING,
    )

    if _store is None:
        yield ToolChunk(
            content=[TextBlock(
                text="[FAIL] Memory store not initialized"
            )],
            state=ToolResultState.ERROR,
        )
        return

    if _store.delete_memory(memory_id):
        yield ToolChunk(
            content=[TextBlock(
                text=f"[ OK ] Memory deleted: {memory_id[:8]}..."
            )],
            state=ToolResultState.SUCCESS,
        )
    else:
        yield ToolChunk(
            content=[TextBlock(
                text=f"[FAIL] Memory not found: {memory_id[:8]}..."
            )],
            state=ToolResultState.ERROR,
        )


async def _update_memory(memory_id: str, content: str | None = None,
                         type: str | None = None,
                         importance: float | None = None,
                         scope: str | None = None) -> ToolChunk:
    """Update an existing memory's content, type, importance, or scope.

    Args:
        memory_id: ID of the memory to update (use list_memories to find IDs).
        content: New content (optional).
        type: New type: episodic | semantic | procedural (optional).
        importance: New importance score 0.0-1.0 (optional).
        scope: New scope: global | session (optional).
    """
    yield ToolChunk(
        content=[TextBlock(
            text=f"[Tool] Updating memory: {memory_id[:8]}..."
        )],
        state=ToolResultState.RUNNING,
    )

    if _store is None:
        yield ToolChunk(
            content=[TextBlock(
                text="[FAIL] Memory store not initialized"
            )],
            state=ToolResultState.ERROR,
        )
        return

    # Build update kwargs
    kwargs = {}
    if content is not None:
        kwargs["content"] = content
    if type is not None:
        kwargs["type"] = type
    if importance is not None:
        kwargs["importance"] = importance
    if scope is not None:
        kwargs["scope"] = scope

    if not kwargs:
        yield ToolChunk(
            content=[TextBlock(
                text="[FAIL] No fields to update (content, type, importance, or scope required)"
            )],
            state=ToolResultState.ERROR,
        )
        return

    if _store.update_memory(memory_id, **kwargs):
        yield ToolChunk(
            content=[TextBlock(
                text=f"[ OK ] Memory updated: {memory_id[:8]}... "
                     f"({', '.join(kwargs.keys())})"
            )],
            state=ToolResultState.SUCCESS,
        )
    else:
        yield ToolChunk(
            content=[TextBlock(
                text=f"[FAIL] Memory not found: {memory_id[:8]}..."
            )],
            state=ToolResultState.ERROR,
        )


def get_memory_tools() -> list[FunctionTool]:
    """Return memory-related FunctionTools for the Toolkit."""
    return [
        FunctionTool(_search_memory),
        FunctionTool(_add_memory),
        FunctionTool(_list_memories),
        FunctionTool(_forget_memory),
        FunctionTool(_update_memory),
    ]