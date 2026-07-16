"""Agent Service entry point.

FastAPI-based HTTP service for Studio mode.
Provides REST, SSE endpoints and a built-in chat web UI.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from agentscope.event import EventType
from agentscope.message import UserMsg

if TYPE_CHECKING:
    from agentscope.agent import Agent

CHAT_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentScope Chat</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#1a1a2e;color:#e0e0e0;height:100vh;display:flex;flex-direction:column}
header{background:#16213e;padding:12px 20px;border-bottom:1px solid #0f3460;display:flex;align-items:center;gap:10px}
header .dot{width:10px;height:10px;border-radius:50%;background:#00ff88;box-shadow:0 0 8px #00ff88}
header h1{font-size:18px;font-weight:600}
header span{font-size:12px;color:#888;margin-left:auto}
#chat{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:12px}
.msg{max-width:80%;padding:10px 14px;border-radius:12px;line-height:1.5;font-size:14px;white-space:pre-wrap;word-break:break-word}
.msg.user{align-self:flex-end;background:#0f3460;border-bottom-right-radius:4px}
.msg.agent{align-self:flex-start;background:#16213e;border-bottom-left-radius:4px}
.msg .label{font-size:11px;color:#888;margin-bottom:4px}
.tool{font-size:12px;color:#ffc107;padding:4px 0}
.tool.ok{color:#00ff88}
.tool.fail{color:#ff4444}
footer{padding:12px 20px;border-top:1px solid #0f3460;display:flex;gap:10px}
footer input{flex:1;padding:10px 14px;border-radius:8px;border:1px solid #0f3460;background:#16213e;color:#e0e0e0;font-size:14px;outline:none}
footer input:focus{border-color:#00ff88}
footer button{padding:10px 20px;border-radius:8px;border:none;background:#00ff88;color:#1a1a2e;font-size:14px;font-weight:600;cursor:pointer}
footer button:disabled{opacity:.5;cursor:not-allowed}
.typing{align-self:flex-start;color:#00ff88;font-size:12px;padding:4px 0}
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
  d.innerHTML='<div class="label">'+(role==='user'?'You':'Agent')+'</div>'+text;
  chat.appendChild(d);
  chat.scrollTop=chat.scrollHeight;
}
function addTool(text,cls){
  const d=document.createElement('div');
  d.className='tool '+(cls||'');
  d.textContent=text;
  chat.appendChild(d);
  chat.scrollTop=chat.scrollHeight;
}
async function send(){
  const text=input.value.trim();
  if(!text||busy)return;
  busy=true;btn.disabled=true;
  addMsg('user',text);
  input.value='';
  const agentDiv=document.createElement('div');
  agentDiv.className='msg agent';
  agentDiv.innerHTML='<div class="label">Agent</div>';
  chat.appendChild(agentDiv);
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
        if(d.type==='text')agentDiv.innerHTML+='<span>'+d.text+'</span>';
        else if(d.type==='tool_start')addTool('[Tool] '+d.name);
        else if(d.type==='tool_result')addTool(d.status+' '+d.name,d.status==='[OK]'?'ok':'fail');
      }
      chat.scrollTop=chat.scrollHeight;
    }
  }catch(e){
    agentDiv.innerHTML+='<span style="color:#ff4444">Error: '+e.message+'</span>';
  }
  busy=false;btn.disabled=false;
  input.focus();
}
</script>
</body>
</html>"""


def create_app(agent: "Agent") -> FastAPI:
    """Create a FastAPI app that wraps the Agent.

    Args:
        agent: Configured Agent instance.

    Returns:
        FastAPI application with /, /chat, /chat/stream, /health endpoints.
    """
    app = FastAPI(title="AgentScope Agent Service")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return CHAT_PAGE

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "agent": agent.name}

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
            async for evt in agent.reply_stream(
                UserMsg("user", content),
            ):
                if evt.type == EventType.TEXT_BLOCK_DELTA and evt.delta:
                    yield _sse({"type": "text", "text": evt.delta})
                elif evt.type == EventType.TOOL_CALL_START:
                    yield _sse(
                        {
                            "type": "tool_start",
                            "name": evt.tool_call_name,
                        }
                    )
                elif evt.type == EventType.TOOL_RESULT_END:
                    status = {
                        "SUCCESS": "[OK]",
                        "ERROR": "[FAIL]",
                        "INTERRUPTED": "[STOP]",
                        "DENIED": "[DENY]",
                    }.get(evt.state.value, "[??]")
                    yield _sse(
                        {
                            "type": "tool_result",
                            "name": evt.state.value,
                            "status": status,
                        }
                    )
            yield _sse({"type": "done"})

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
        )

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
    from app.tools import build_toolkit

    async def _run() -> None:
        config = load_config()
        toolkit = await build_toolkit(config)
        agent = build_agent(config, toolkit)
        app = create_app(agent)
        uvicorn_config = uvicorn.Config(app, host="0.0.0.0", port=8000)
        server = uvicorn.Server(uvicorn_config)
        await server.serve()

    import asyncio

    asyncio.run(_run())


if __name__ == "__main__":
    main()