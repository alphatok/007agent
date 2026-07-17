"""Agent Service entry point.

FastAPI-based HTTP service for Studio mode.
Provides REST, SSE endpoints and a built-in chat web UI with:
- Real-time markdown rendering
- File download support
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from agentscope.event import EventType
from agentscope.message import UserMsg

from app.task_manager import TaskManager

if TYPE_CHECKING:
    from agentscope.agent import Agent
    from app.store import SessionStore
    from app.memory import MemoryStore

# Workspace root for file downloads
WORKSPACE_ROOT = Path.cwd()

CHAT_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentScope Chat</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;height:100vh;display:flex;flex-direction:column}
header{background:#161b22;padding:12px 20px;border-bottom:1px solid #30363d;display:flex;align-items:center;gap:10px}
header .dot{width:10px;height:10px;border-radius:50%;background:#3fb950;box-shadow:0 0 8px #3fb950}
header h1{font-size:18px;font-weight:600;color:#f0f6fc}
header span{font-size:12px;color:#8b949e;margin-left:auto}
#chat{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:16px}
.msg{max-width:88%;padding:12px 16px;border-radius:12px;line-height:1.65;font-size:14px;word-break:break-word}
.msg.user{align-self:flex-end;background:#1f6feb;border-bottom-right-radius:4px;color:#fff}
.msg.agent{align-self:flex-start;background:#161b22;border:1px solid #30363d;border-bottom-left-radius:4px}
.msg .label{font-size:11px;color:#8b949e;margin-bottom:8px;font-weight:500;letter-spacing:.5px;text-transform:uppercase}
.msg.agent .content{color:#c9d1d9}
/* Markdown - Headings */
.msg.agent .content h1{font-size:20px;margin:16px 0 8px;padding-bottom:6px;border-bottom:1px solid #21262d;color:#f0f6fc;font-weight:600}
.msg.agent .content h2{font-size:17px;margin:14px 0 6px;padding-bottom:4px;border-bottom:1px solid #21262d;color:#f0f6fc;font-weight:600}
.msg.agent .content h3{font-size:15px;margin:12px 0 4px;color:#f0f6fc;font-weight:600}
.msg.agent .content h4{font-size:14px;margin:10px 0 4px;color:#f0f6fc;font-weight:600}
/* Markdown - Text */
.msg.agent .content p{margin:6px 0}
.msg.agent .content strong{color:#f0f6fc}
.msg.agent .content em{color:#d2a8ff}
/* Markdown - Lists */
.msg.agent .content ul,.msg.agent .content ol{padding-left:24px;margin:6px 0}
.msg.agent .content li{margin:3px 0}
.msg.agent .content li::marker{color:#8b949e}
/* Markdown - Code */
.msg.agent .content code{background:#1c2128;padding:2px 6px;border-radius:4px;font-size:85%;font-family:'SF Mono',Monaco,Menlo,Consolas,monospace;color:#d2a8ff;border:1px solid #30363d}
.msg.agent .content pre{background:#161b22;padding:14px 16px;border-radius:8px;overflow-x:auto;margin:8px 0;font-size:13px;border:1px solid #30363d;line-height:1.5}
.msg.agent .content pre code{background:none;padding:0;border:none;color:#c9d1d9;font-size:inherit}
/* Markdown - Blockquote */
.msg.agent .content blockquote{border-left:3px solid #3fb950;padding:6px 14px;margin:8px 0;color:#8b949e;background:#1c2128;border-radius:0 6px 6px 0}
.msg.agent .content blockquote p{margin:2px 0}
/* Markdown - Links */
.msg.agent .content a{color:#58a6ff;text-decoration:none}
.msg.agent .content a:hover{text-decoration:underline}
/* Markdown - Tables */
.msg.agent .content table{border-collapse:collapse;margin:8px 0;width:100%;font-size:13px}
.msg.agent .content th{background:#1c2128;color:#f0f6fc;font-weight:600;padding:8px 12px;border:1px solid #30363d;text-align:left}
.msg.agent .content td{padding:7px 12px;border:1px solid #30363d}
.msg.agent .content tr:nth-child(even){background:#161b22}
.msg.agent .content tr:hover{background:#1c2128}
/* Markdown - Horizontal rule */
.msg.agent .content hr{border:none;border-top:1px solid #30363d;margin:12px 0}
/* Markdown - Images */
.msg.agent .content img{max-width:100%;border-radius:8px;margin:4px 0}
/* Tool status */
.tool{font-size:12px;padding:3px 0;display:flex;align-items:center;gap:6px}
.tool .icon{min-width:44px;font-weight:600;font-size:11px}
.tool .icon.start{color:#d29922}
.tool .icon.ok{color:#3fb950}
.tool .icon.fail{color:#f85149}
.tool .name{color:#8b949e}
/* Download button */
.dl-btn{display:inline-flex;align-items:center;gap:5px;margin:6px 6px 0 0;padding:5px 12px;font-size:12px;background:#1c2128;color:#3fb950;border:1px solid #30363d;border-radius:6px;cursor:pointer;text-decoration:none;transition:all .15s}
.dl-btn:hover{background:#238636;color:#fff;border-color:#238636}
/* Input */
footer{padding:12px 20px;border-top:1px solid #30363d;background:#161b22;display:flex;gap:10px}
footer input{flex:1;padding:10px 14px;border-radius:8px;border:1px solid #30363d;background:#0d1117;color:#c9d1d9;font-size:14px;outline:none;transition:border-color .15s}
footer input:focus{border-color:#58a6ff;box-shadow:0 0 0 3px rgba(88,166,255,.15)}
footer button{padding:10px 20px;border-radius:8px;border:1px solid #238636;background:#238636;color:#fff;font-size:14px;font-weight:600;cursor:pointer;transition:all .15s}
footer button:hover{background:#2ea043}
footer button:disabled{opacity:.5;cursor:not-allowed}
/* Scrollbar */
#chat::-webkit-scrollbar{width:6px}
#chat::-webkit-scrollbar-track{background:transparent}
#chat::-webkit-scrollbar-thumb{background:#30363d;border-radius:3px}
</style>
</head>
<body>
<header>
  <div class="dot"></div>
  <h1>AgentScope Chat</h1>
  <span>DeepSeek V4 Pro</span>
</header>
<div id="chat"></div>
<footer>
  <input id="input" placeholder="Type a message..." autofocus>
  <button id="send" onclick="send()">Send</button>
</footer>
<script>
const chat=document.getElementById('chat');
const input=document.getElementById('input');
const btn=document.getElementById('send');
let busy=false;
input.addEventListener('keydown',e=>{if(e.key==='Enter')send()});
function addMsg(role,text){
  const d=document.createElement('div');
  d.className='msg '+role;
  const label=role==='user'?'You':'Agent';
  d.innerHTML='<div class="label">'+label+'</div><div class="content">'+text+'</div>';
  chat.appendChild(d);
  chat.scrollTop=chat.scrollHeight;
  return d;
}
function addTool(text,cls){
  const d=document.createElement('div');
  d.className='tool';
  const iconCls=cls||'start';
  d.innerHTML='<span class="icon '+iconCls+'">'+text.split(' ')[0]+'</span><span class="name">'+text.split(' ').slice(1).join(' ')+'</span>';
  chat.appendChild(d);
  chat.scrollTop=chat.scrollHeight;
  return d;
}
function addDlBtn(parent,path,label){
  const a=document.createElement('a');
  a.className='dl-btn';
  a.href='/api/files/download?path='+encodeURIComponent(path);
  a.download=path.split('/').pop();
  a.textContent='\\u2b07 '+label;
  parent.appendChild(a);
}
// Detect file paths in text and add download buttons
function detectFiles(text,parent){
  const re=/\\b([\\/]\\S+?\\.\\w+)\\b/g;
  const seen=new Set();
  let m;
  while((m=re.exec(text))!==null){
    const p=m[1];
    if(!seen.has(p)){
      seen.add(p);
      addDlBtn(parent,p,p.split('/').pop());
    }
  }
}
async function send(){
  const text=input.value.trim();
  if(!text||busy)return;
  busy=true;btn.disabled=true;
  addMsg('user',text);
  input.value='';
  const agentDiv=document.createElement('div');
  agentDiv.className='msg agent';
  agentDiv.innerHTML='<div class="label">Agent</div><div class="content"></div>';
  chat.appendChild(agentDiv);
  const contentDiv=agentDiv.querySelector('.content');
  let rawText='';
  // Render markdown on each delta
  function renderMd(){
    if(rawText) contentDiv.innerHTML=marked.parse(rawText);
  }
  try{
    const r=await fetch('/chat/stream',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({content:text})
    });
    const reader=r.body.getReader();
    const decoder=new TextDecoder();
    let buffer='';
    while(true){
      const{done,value}=await reader.read();
      if(done)break;
      buffer+=decoder.decode(value,{stream:true});
      const lines=buffer.split('\\n');
      buffer=lines.pop()||'';
      for(const line of lines){
        if(!line.startsWith('data:'))continue;
        const d=JSON.parse(line.slice(5).trim());
        if(d.type==='text'){
          rawText+=d.text;
          renderMd();
        }else if(d.type==='tool_start'){
          addTool('[Tool] '+d.name);
        }else if(d.type==='tool_result'){
          addTool(d.status+' '+d.name,d.status==='[OK]'?'ok':d.status==='[FAIL]'?'fail':'start');
        }else if(d.type==='tool_output'){
          addTool('  '+d.text.substring(0,120),'start');
        }
      }
      chat.scrollTop=chat.scrollHeight;
    }
    // Final render + file detection
    renderMd();
    detectFiles(rawText,contentDiv);
  }catch(e){
    contentDiv.innerHTML='<span style="color:#ff4444">Error: '+e.message+'</span>';
  }
  busy=false;btn.disabled=false;
  input.focus();
}
</script>
</body>
</html>"""


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
    root = workspace_root or WORKSPACE_ROOT

    app = FastAPI(title="AgentScope Agent Service")

    # --- Web UI ---

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return CHAT_PAGE

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
            _last_summary: str | None = agent.state.summary
            async for evt in agent.reply_stream(
                UserMsg("user", content),
            ):
                # Detect context compaction
                current_summary = agent.state.summary
                if current_summary != _last_summary:
                    _last_summary = current_summary
                    if current_summary:
                        yield _sse({
                            "type": "compaction",
                            "status": "completed",
                            "summary": "Context compressed",
                        })

                if evt.type == EventType.TEXT_BLOCK_DELTA and evt.delta:
                    yield _sse({"type": "text", "text": evt.delta})
                elif evt.type == EventType.TOOL_CALL_START:
                    yield _sse({
                        "type": "tool_start",
                        "name": evt.tool_call_name,
                    })
                elif evt.type == EventType.TOOL_RESULT_TEXT_DELTA and evt.delta:
                    yield _sse({
                        "type": "tool_output",
                        "text": evt.delta.strip()[:200],
                    })
                elif evt.type == EventType.TOOL_RESULT_END:
                    state = evt.state.value
                    status_map = {
                        "SUCCESS": "[OK]",
                        "ERROR": "[FAIL]",
                        "INTERRUPTED": "[STOP]",
                        "DENIED": "[DENY]",
                    }
                    yield _sse({
                        "type": "tool_result",
                        "name": state,
                        "status": status_map.get(state, "[??]"),
                    })
            yield _sse({"type": "done"})

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
        )

    # --- Async Tasks ---

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

    # ---- Session API ----

    @app.get("/api/sessions")
    async def list_sessions(limit: int = Query(50, ge=1, le=200)):
        """List all sessions."""
        if not store:
            return []
        return store.list_sessions(limit=limit)

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


def main() -> None:
    """Start the Agent Service."""
    import uvicorn

    from app.agent import build_agent
    from app.config import load_config
    from app.memory import MemoryStore
    from app.memory_tool import set_memory_store, set_retriever
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

        toolkit = await build_toolkit(config)
        agent = await build_agent(
            config, toolkit, store=store, memory=memory,
        )
        tm = TaskManager()
        app = create_app(
            agent, task_manager=tm, store=store, memory=memory,
        )
        uvicorn_config = uvicorn.Config(app, host="0.0.0.0", port=8000)
        server = uvicorn.Server(uvicorn_config)
        await server.serve()

    import asyncio

    asyncio.run(_run())


if __name__ == "__main__":
    main()