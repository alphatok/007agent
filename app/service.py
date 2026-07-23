"""Agent Service entry point.

FastAPI-based HTTP service for Studio mode.
Provides REST, SSE endpoints and a built-in chat web UI with:
- Real-time markdown rendering
- File download support
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agentscope.event import EventType
from agentscope.message import UserMsg

from app.checkpoint import load_checkpoint
from app.memory_tool import set_current_session_id
from app.task_manager import TaskManager

if TYPE_CHECKING:
    from agentscope.agent import Agent
    from app.store import SessionStore
    from app.memory import MemoryStore

# Static files directory
_STATIC_DIR = Path(__file__).parent / "static"


def _load_chat_html() -> str:
    """Load chat.html from static directory."""
    html_path = _STATIC_DIR / "chat.html"
    return html_path.read_text(encoding="utf-8")


def _read_active_session(data_dir: str) -> str | None:
    """Read active session ID from file."""
    active_file = os.path.join(data_dir, "active_session.txt")
    if not os.path.exists(active_file):
        return None
    try:
        with open(active_file, "r") as f:
            sid = f.read().strip()
            return sid if sid else None
    except (OSError, UnicodeDecodeError):
        return None


def _write_active_session(data_dir: str, session_id: str) -> None:
    """Write active session ID to file."""
    active_file = os.path.join(data_dir, "active_session.txt")
    with open(active_file, "w") as f:
        f.write(session_id)


def create_app(
    agent: "Agent",
    task_manager: TaskManager | None = None,
    workspace_root: Path | None = None,
    store: "SessionStore | None" = None,
    memory: "MemoryStore | None" = None,
) -> FastAPI:
    """Create a FastAPI app that wraps the Agent.

    Args:
        agent: Configured Agent instance.
        task_manager: Optional TaskManager for async task API.
        workspace_root: Root directory for file downloads. Defaults to CWD.
        store: Optional SessionStore for session persistence.
        memory: Optional MemoryStore for cross-session memory.

    Returns:
        FastAPI application with web UI, chat, and file download endpoints.
    """
    root = workspace_root

    app = FastAPI(title="AgentScope Agent Service")

    # --- Web UI ---

    # Mount static files for CSS, JS, etc.
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return _load_chat_html()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "agent": agent.name}

    # --- File Download ---

    @app.get("/api/files/download")
    async def download_file(path: str = Query(...)) -> FileResponse:
        """Download a file from the workspace."""
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = root / file_path
        # Security: ensure path is within workspace
        try:
            file_path.resolve().relative_to(root.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Path outside workspace")
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(
            file_path,
            filename=file_path.name,
            media_type="application/octet-stream",
        )

    @app.get("/api/files/list")
    async def list_files() -> list[dict]:
        """List recently modified files in workspace."""
        files = []
        for p in sorted(root.rglob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.is_file() and not p.name.startswith(".") and ".venv" not in p.parts:
                files.append({
                    "path": str(p),
                    "name": p.name,
                    "size": p.stat().st_size,
                })
                if len(files) >= 20:
                    break
        return files

    # --- Chat ---

    @app.post("/chat")
    async def chat(request: dict) -> dict:
        content = request.get("content", "")
        if not content:
            return {"error": "content is required"}
        reply = await agent.reply(UserMsg("user", content))
        return {"reply": str(reply)}

    @app.post("/chat/stream")
    async def chat_stream(request: Request) -> StreamingResponse:
        body = await request.json()
        content = body.get("content", "")
        if not content:
            return StreamingResponse(
                _sse_error("content is required"),
                media_type="text/event-stream",
            )

        async def generate():
            # Use active session (persisted across restarts)
            session_id = getattr(agent, "_active_session_id", None)
            if not session_id:
                session_id = store.create_session(name="web-chat") if store else ""
                if store:
                    pass  # active_session already written on startup
                object.__setattr__(agent, "_active_session_id", session_id)

            # Inject current session ID for memory tools
            set_current_session_id(session_id)

            # Persist user message
            if store and session_id:
                store.save_message(session_id, "user", content)

            _last_summary: str | None = agent.state.summary
            full_reply = ""
            # Track active tool calls for grouping
            tool_call_names: dict[str, str] = {}
            # Track thinking state
            _thinking_active = False
            async for evt in agent.reply_stream(
                UserMsg("user", content),
            ):
                # Detect context compaction (only when summary actually changes
                # from a non-None value, indicating real compaction happened)
                current_summary = agent.state.summary
                if (_last_summary is not None
                        and current_summary != _last_summary
                        and current_summary):
                    _last_summary = current_summary
                    yield _sse({"type": "compaction"})
                elif current_summary is not None:
                    _last_summary = current_summary

                if evt.type == EventType.TEXT_BLOCK_DELTA and evt.delta:
                    full_reply += evt.delta
                    yield _sse({"type": "text", "text": evt.delta})
                elif evt.type == EventType.THINKING_BLOCK_START:
                    _thinking_active = True
                    yield _sse({"type": "thinking_start"})
                elif evt.type == EventType.THINKING_BLOCK_DELTA and evt.delta:
                    yield _sse({"type": "thinking", "text": evt.delta})
                elif evt.type == EventType.THINKING_BLOCK_END:
                    _thinking_active = False
                    yield _sse({"type": "thinking_end"})
                elif evt.type == EventType.TOOL_CALL_START:
                    tid = evt.tool_call_id
                    tname = evt.tool_call_name
                    tool_call_names[tid] = tname
                    yield _sse({
                        "type": "tool_start",
                        "tool_call_id": tid,
                        "name": tname,
                    })
                elif evt.type == EventType.TOOL_RESULT_TEXT_DELTA and evt.delta:
                    output = evt.delta.strip()
                    # Detect binary content
                    if _is_binary(output):
                        output = "[binary output]"
                    elif len(output) > 300:
                        output = output[:300] + "..."
                    yield _sse({
                        "type": "tool_output",
                        "tool_call_id": evt.tool_call_id,
                        "text": output,
                    })
                elif evt.type == EventType.TOOL_RESULT_END:
                    tid = evt.tool_call_id
                    state = evt.state
                    tname = tool_call_names.get(tid, "unknown")
                    status_map = {
                        "SUCCESS": "[OK]",
                        "ERROR": "[FAIL]",
                        "INTERRUPTED": "[STOP]",
                        "DENIED": "[DENY]",
                    }
                    yield _sse({
                        "type": "tool_result",
                        "tool_call_id": tid,
                        "name": tname,
                        "status": status_map.get(state, "[??]"),
                    })

            # Persist assistant reply
            if store and full_reply.strip():
                store.save_message(session_id, "assistant", full_reply.strip())

            yield _sse({"type": "done"})

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
        )

    # --- Async Tasks ---
    # NOTE: Static routes must be registered BEFORE parameterized routes
    # to avoid FastAPI matching "pending-questions" as a task_id.

    @app.post("/api/tasks")
    async def submit_task(request: dict) -> dict:
        """Submit an async task. Returns task_id immediately."""
        if not task_manager:
            raise HTTPException(
                status_code=501,
                detail="Task manager not configured",
            )
        content = request.get("content", "")
        if not content:
            raise HTTPException(status_code=400, detail="content is required")
        subagent = request.get("subagent")
        task = task_manager.create(content=content, subagent=subagent)
        task_manager.start_execute(task, agent)
        return {
            "task_id": task.task_id,
            "status": task.status,
            "created_at": task.created_at,
            "status_url": f"/api/tasks/{task.task_id}",
        }

    @app.get("/api/tasks")
    async def list_tasks() -> list[dict]:
        """List all tasks, newest first."""
        if not task_manager:
            raise HTTPException(
                status_code=501,
                detail="Task manager not configured",
            )
        from dataclasses import asdict
        return [asdict(t) for t in task_manager.list_all()]

    @app.get("/api/tasks/pending-questions")
    async def get_pending_questions():
        """Get all pending questions waiting for user input."""
        from app.tools import get_pending_questions

        return get_pending_questions()

    @app.get("/api/tasks/{task_id}")
    async def get_task(task_id: str) -> dict:
        """Get task status and result by ID."""
        if not task_manager:
            raise HTTPException(
                status_code=501,
                detail="Task manager not configured",
            )
        task = task_manager.get(task_id)
        if task is None:
            raise HTTPException(
                status_code=404,
                detail=f"Task '{task_id}' not found",
            )
        from dataclasses import asdict
        return asdict(task)

    @app.delete("/api/tasks/{task_id}")
    async def cancel_task(task_id: str) -> dict:
        """Cancel or delete a task."""
        if not task_manager:
            raise HTTPException(
                status_code=501,
                detail="Task manager not configured",
            )
        task = task_manager.get(task_id)
        if task is None:
            raise HTTPException(
                status_code=404,
                detail=f"Task '{task_id}' not found",
            )
        if task.status in ("running", "pending"):
            task_manager.update(task_id, status="cancelled")
        task_manager.delete(task_id)
        return {"task_id": task_id, "status": "cancelled"}

    @app.post("/api/tasks/{task_id}/respond")
    async def respond_to_task(task_id: str, request: Request):
        """Respond to a task waiting for user input."""
        from app.tools import set_user_response

        body = await request.json()
        response = body.get("response", "")
        success = set_user_response(task_id, response)
        if success:
            return {"status": "ok", "message": "Response received"}
        else:
            raise HTTPException(
                status_code=404,
                detail="No pending question found for this task_id",
            )

    @app.get("/api/tasks/{task_id}/stream")
    async def stream_task_progress(task_id: str) -> StreamingResponse:
        """Stream task progress via SSE."""
        if not task_manager:
            raise HTTPException(
                status_code=501,
                detail="Task manager not configured",
            )
        task = task_manager.get(task_id)
        if task is None:
            raise HTTPException(
                status_code=404,
                detail=f"Task '{task_id}' not found",
            )

        async def generate():
            queue = task_manager.progress_queue(task_id)
            # Send initial state
            yield _sse({
                "type": "progress",
                "progress": task.progress,
                "current_step": task.current_step,
                "status": task.status,
            })
            completed_steps = 0
            try:
                while True:
                    event = await queue.get()
                    # Support parallel subtask progress with step_id
                    if event.get("step_id"):
                        completed_steps += 1
                        overall = int(completed_steps / max(event.get("total_steps", 1), 1) * 100)
                        event["progress"] = overall
                    yield _sse(event)
                    if event["type"] in ("done", "error"):
                        break
            except asyncio.CancelledError:
                yield _sse({"type": "error", "error": "Connection closed"})
            except Exception as e:
                yield _sse({"type": "error", "error": str(e)})

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
        )

    # ---- Session API ----

    @app.get("/api/sessions")
    async def list_sessions(limit: int = Query(50, ge=1, le=200)):
        """List all sessions with display_name."""
        if not store:
            return []
        sessions = store.list_sessions(limit=limit)
        for s in sessions:
            first_msg = store.get_first_user_message(s["id"])
            if first_msg:
                s["display_name"] = first_msg[:30] + ("..." if len(first_msg) > 30 else "")
            else:
                s["display_name"] = f"Session {s['created_at'][:19]}"
        return sessions

    @app.post("/api/sessions")
    async def create_session(
        name: str = Query("", description="Session name"),
    ):
        """Create a new session."""
        if not store:
            raise HTTPException(status_code=501, detail="Store not configured")
        session_id = store.create_session(name=name or None)
        session = store.get_session(session_id)
        return {"session_id": session_id, "session": session}

    # ---- Active Session API ----

    @app.get("/api/sessions/active")
    async def get_active_session(
        limit: int = Query(50, ge=1, le=100),
    ):
        """Get active session with recent ."""
        if not store:
            raise HTTPException(status_code=501, detail="Store not configured")
        session_id = getattr(agent, "_active_session_id", None)
        if not session_id:
            session_id = store.create_session()
            _write_active_session(os.path.dirname(store._db_path), session_id)
            object.__setattr__(agent, "_active_session_id", session_id)
        session = store.get_session(session_id)
        messages = store.get_messages(session_id, limit=limit)
        return {
            "session_id": session_id,
            "session": session,
            "messages": messages,
        }


    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str):
        """Get session details."""
        if not store:
            raise HTTPException(status_code=501, detail="Store not configured")
        session = store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return session

    @app.get("/api/sessions/{session_id}/messages")
    async def get_session_messages(
        session_id: str,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
    ):
        """Get messages for a session."""
        if not store:
            raise HTTPException(status_code=501, detail="Store not configured")
        return store.get_messages(session_id, limit=limit, offset=offset)

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str):
        """Delete a session."""
        if not store:
            raise HTTPException(status_code=501, detail="Store not configured")
        if not store.delete_session(session_id):
            raise HTTPException(status_code=404, detail="Session not found")
        return {"deleted": session_id}

    @app.post("/api/sessions/{session_id}/resume")
    async def resume_session(session_id: str):
        """Resume (load) a session into agent context."""
        if not store:
            raise HTTPException(status_code=501, detail="Store not configured")
        if store.load_session(session_id, agent):
            return {"resumed": session_id}
        raise HTTPException(status_code=404, detail="Session not found")

    @app.post("/api/sessions/new")
    async def new_session():
        """Create a new session and set it as active."""
        if not store:
            raise HTTPException(status_code=501, detail="Store not configured")
        # Clear agent context
        agent.state.context.clear()
        # Create new session
        session_id = store.create_session()
        _write_active_session(os.path.dirname(store._db_path), session_id)
        object.__setattr__(agent, "_active_session_id", session_id)
        return {
            "session_id": session_id,
            "session": store.get_session(session_id),
        }

    @app.post("/api/sessions/{session_id}/switch")
    async def switch_session(session_id: str):
        """Switch to a different session (validate first, then clear+load)."""
        if not store:
            raise HTTPException(status_code=501, detail="Store not configured")
        # Validate target session exists first
        session = store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        # Safe to switch
        agent.state.context.clear()
        store.load_session(session_id, agent, limit=50)
        _write_active_session(os.path.dirname(store._db_path), session_id)
        object.__setattr__(agent, "_active_session_id", session_id)
        return {
            "session_id": session_id,
            "session": session,
            "messages": store.get_messages(session_id, limit=50),
        }

    # ---- Memory API ----

    @app.get("/api/memories")
    async def list_memories(
        type: str = Query("all", description="Memory type filter"),
        limit: int = Query(50, ge=1, le=200),
    ):
        """List memories."""
        if not memory:
            return []
        return memory.list_memories(
            type=None if type == "all" else type, limit=limit,
        )

    @app.post("/api/memories")
    async def add_memory(
        content: str = Query(..., description="Memory content"),
        type: str = Query("semantic", description="Memory type"),
        importance: float = Query(0.5, ge=0.0, le=1.0),
    ):
        """Add a memory."""
        if not memory:
            raise HTTPException(status_code=501, detail="Memory not configured")
        memory_id = memory.add_memory(
            type=type, content=content, importance=importance,
        )
        return {"memory_id": memory_id}

    @app.get("/api/memories/search")
    async def search_memories(
        q: str = Query(..., description="Search query"),
        type: str = Query("all", description="Memory type filter"),
        top_k: int = Query(10, ge=1, le=50),
    ):
        """Search memories (hybrid retrieval)."""
        if not memory:
            return []
        from app.retriever import HybridRetriever

        retriever = HybridRetriever(
            memory._db_path, memory._zvec_path, memory,
        )
        types = None if type == "all" else [type]
        return retriever.search(q, top_k=top_k, memory_types=types)

    @app.delete("/api/memories/{memory_id}")
    async def delete_memory(memory_id: str):
        """Delete a memory."""
        if not memory:
            raise HTTPException(status_code=501, detail="Memory not configured")
        if not memory.delete_memory(memory_id):
            raise HTTPException(status_code=404, detail="Memory not found")
        return {"deleted": memory_id}

    return app


def _sse(data: dict) -> str:
    """Format data as an SSE event."""
    import json

    return f"data: {json.dumps(data)}\n\n"


def _sse_error(message: str) -> str:
    """Format an SSE error event."""
    return _sse({"type": "error", "text": message})


def _is_binary(text: str) -> bool:
    """Detect if text contains binary data."""
    if not text:
        return False
    # Check for null bytes or high concentration of non-printable chars
    non_printable = sum(1 for c in text if ord(c) < 9 or (13 < ord(c) < 32))
    if non_printable > len(text) * 0.3:
        return True
    # Check for typical binary markers
    if "\x00" in text:
        return True
    return False


def main() -> None:
    """Start the Agent Service."""
    import uvicorn

    from app.agent import build_agent
    from app.config import load_config
    from app.memory import MemoryStore
    from app.memory_tool import set_memory_store, set_retriever, set_current_session_id
    from app.retriever import HybridRetriever
    from app.store import SessionStore
    from app.tools import build_toolkit

    async def _run() -> None:
        config = load_config()

        # Initialize persistence
        os.makedirs(config.data_dir, exist_ok=True)
        store = SessionStore(config.db_path)
        memory = MemoryStore(config.db_path, config.zvec_path)
        retriever = HybridRetriever(
            config.db_path, config.zvec_path, memory,
        )
        set_memory_store(memory)
        set_retriever(retriever)

        toolkit, mcp_clients = await build_toolkit(config)
        agent = await build_agent(
            config, toolkit, store=store, memory=memory,
        )

        # Recover active session
        session_id = _read_active_session(config.data_dir)
        if session_id and store.get_session(session_id):
            store.load_session(session_id, agent, limit=50)
        else:
            session_id = store.create_session()
            _write_active_session(config.data_dir, session_id)
        object.__setattr__(agent, "_active_session_id", session_id)
        tm = TaskManager()

        # Check for unfinished tasks at startup
        pending_tasks = [t for t in tm.list_all() if t.status == "pending"]
        if pending_tasks:
            logger.info(f"Found {len(pending_tasks)} pending tasks from previous session")
            # Try to resume each pending task
            for task in pending_tasks:
                checkpoint = load_checkpoint(config.data_dir, task.task_id)
                if checkpoint:
                    logger.info(f"Resuming task {task.task_id} from checkpoint (step {checkpoint.step_index})")
                    tm.resume_task(task.task_id, agent)

        app = create_app(
            agent, task_manager=tm, store=store, memory=memory,
            workspace_root=Path(config.workspace_root).resolve(),
        )
        uvicorn_config = uvicorn.Config(app, host="0.0.0.0", port=8000)
        server = uvicorn.Server(uvicorn_config)
        try:
            await server.serve()
        finally:
            for mcp in mcp_clients:
                try:
                    await mcp.close()
                except Exception:
                    pass

    import asyncio

    asyncio.run(_run())


if __name__ == "__main__":
    main()