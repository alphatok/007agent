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

from agentscope.event import EventType
from agentscope.message import UserMsg

from app.checkpoint import load_checkpoint
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
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;height:100vh;display:flex}
/* Sidebar */
#sidebar{width:240px;min-width:240px;background:#161b22;border-right:1px solid #30363d;display:flex;flex-direction:column;overflow:hidden}
#sidebar .brand{padding:14px 16px;border-bottom:1px solid #30363d;display:flex;align-items:center;gap:8px}
#sidebar .brand .dot{width:8px;height:8px;border-radius:50%;background:#3fb950;box-shadow:0 0 6px #3fb950}
#sidebar .brand span{font-size:14px;font-weight:600;color:#f0f6fc}
#sidebar .new-btn{margin:10px 12px;padding:8px 0;border-radius:6px;border:1px solid #30363d;background:#21262d;color:#c9d1d9;font-size:13px;cursor:pointer;text-align:center;transition:background .15s}
#sidebar .new-btn:hover{background:#30363d}
#session-list{flex:1;overflow-y:auto;padding:0 8px}
#session-list .item{padding:10px 12px;margin:2px 0;border-radius:6px;cursor:pointer;font-size:13px;color:#8b949e;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;transition:background .1s}
#session-list .item:hover{background:#21262d;color:#c9d1d9}
#session-list .item.active{background:#1f6feb22;color:#58a6ff;border:1px solid #1f6feb44}
#session-list .item .time{font-size:11px;color:#484f58;margin-top:2px}
/* Main Chat */
#main{flex:1;display:flex;flex-direction:column;overflow:hidden}
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
.msg.agent .content h1{font-size:20px;margin:16px 0 8px;padding-bottom:6px;border-bottom:1px solid #21262d;color:#f0f6fc;font-weight:600}
.msg.agent .content h2{font-size:17px;margin:14px 0 6px;padding-bottom:4px;border-bottom:1px solid #21262d;color:#f0f6fc;font-weight:600}
.msg.agent .content h3{font-size:15px;margin:12px 0 4px;color:#f0f6fc;font-weight:600}
.msg.agent .content h4{font-size:14px;margin:10px 0 4px;color:#f0f6fc;font-weight:600}
.msg.agent .content p{margin:6px 0}
.msg.agent .content strong{color:#f0f6fc}
.msg.agent .content em{color:#d2a8ff}
.msg.agent .content ul,.msg.agent .content ol{padding-left:24px;margin:6px 0}
.msg.agent .content li{margin:3px 0}
.msg.agent .content li::marker{color:#8b949e}
.msg.agent .content code{background:#1c2128;padding:2px 6px;border-radius:4px;font-size:85%;font-family:'SF Mono',Monaco,Menlo,Consolas,monospace;color:#d2a8ff;border:1px solid #30363d}
.msg.agent .content pre{background:#161b22;padding:14px 16px;border-radius:8px;overflow-x:auto;margin:8px 0;font-size:13px;border:1px solid #30363d;line-height:1.5}
.msg.agent .content pre code{background:none;padding:0;border:none;color:#c9d1d9;font-size:inherit}
.msg.agent .content blockquote{border-left:3px solid #3fb950;padding:6px 14px;margin:8px 0;color:#8b949e;background:#1c2128;border-radius:0 6px 6px 0}
.msg.agent .content blockquote p{margin:2px 0}
.msg.agent .content a{color:#58a6ff;text-decoration:none}
.msg.agent .content a:hover{text-decoration:underline}
.msg.agent .content table{border-collapse:collapse;margin:8px 0;width:100%;font-size:13px}
.msg.agent .content th{background:#1c2128;color:#f0f6fc;font-weight:600;padding:8px 12px;border:1px solid #30363d;text-align:left}
.msg.agent .content td{padding:7px 12px;border:1px solid #30363d}
.msg.agent .content tr:nth-child(even){background:#161b22}
.msg.agent .content tr:hover{background:#1c2128}
.msg.agent .content hr{border:none;border-top:1px solid #30363d;margin:12px 0}
.msg.agent .content img{max-width:100%;border-radius:8px;margin:4px 0}
/* Tool Cards */
.tool-card{margin:8px 0;border:1px solid #30363d;border-radius:8px;overflow:hidden;background:#161b22;font-size:12px;animation:slideIn .2s ease}
.tool-card .tc-header{display:flex;align-items:center;gap:8px;padding:8px 12px;cursor:pointer;transition:background .1s;user-select:none}
.tool-card .tc-header:hover{background:#1c2128}
.tool-card .tc-icon{width:18px;height:18px;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;flex-shrink:0}
.tool-card .tc-icon.running{background:#d2992222;color:#d29922}
.tool-card .tc-icon.ok{background:#3fb95022;color:#3fb950}
.tool-card .tc-icon.fail{background:#f8514922;color:#f85149}
.tool-card .tc-icon.stop{background:#8b949e22;color:#8b949e}
.tool-card .tc-name{color:#e6edf3;font-weight:500;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tool-card .tc-status{font-size:11px;padding:2px 8px;border-radius:10px;font-weight:600}
.tool-card .tc-status.ok{color:#3fb950;background:#3fb95018}
.tool-card .tc-status.fail{color:#f85149;background:#f8514918}
.tool-card .tc-status.running{color:#d29922;background:#d2992218}
.tool-card .tc-status.stop{color:#8b949e;background:#8b949e18}
.tool-card .tc-chevron{color:#484f58;transition:transform .2s;font-size:10px}
.tool-card.expanded .tc-chevron{transform:rotate(180deg)}
.tool-card .tc-body{display:none;padding:0 12px 10px;border-top:1px solid #21262d}
.tool-card.expanded .tc-body{display:block}
.tool-card .tc-body .tc-output{font-family:'SF Mono',Monaco,Menlo,Consolas,monospace;font-size:11px;color:#8b949e;white-space:pre-wrap;word-break:break-all;max-height:200px;overflow-y:auto;line-height:1.5;margin-top:6px;padding:8px;background:#0d1117;border-radius:4px;border:1px solid #21262d}
.tool-card .tc-body .tc-output.binary{color:#f85149;font-style:italic}
.tool-card .tc-body .tc-output::-webkit-scrollbar{width:4px}
.tool-card .tc-body .tc-output::-webkit-scrollbar-thumb{background:#30363d;border-radius:2px}
.tool-card .tc-empty{color:#484f58;font-style:italic;padding:4px 0}
.dl-btn{display:inline-flex;align-items:center;gap:5px;margin:6px 6px 0 0;padding:5px 12px;font-size:12px;background:#1c2128;color:#3fb950;border:1px solid #30363d;border-radius:6px;cursor:pointer;text-decoration:none;transition:background .15s}
.dl-btn:hover{background:#238636;color:#fff;border-color:#238636}
footer{padding:12px 20px;border-top:1px solid #30363d;background:#161b22;display:flex;gap:10px}
footer input{flex:1;padding:10px 14px;border-radius:8px;border:1px solid #30363d;background:#0d1117;color:#c9d1d9;font-size:14px;outline:none;transition:border-color .15s}
footer input:focus{border-color:#58a6ff;box-shadow:0 0 0 3px rgba(88,166,255,.15)}
footer button{padding:10px 20px;border-radius:8px;border:1px solid #238636;background:#238636;color:#fff;font-size:14px;font-weight:600;cursor:pointer;transition:background .15s}
footer button:hover{background:#2ea043}
footer button:disabled{opacity:.5;cursor:not-allowed}
#chat::-webkit-scrollbar{width:6px}
#chat::-webkit-scrollbar-track{background:transparent}
#chat::-webkit-scrollbar-thumb{background:#30363d;border-radius:3px}
#session-list::-webkit-scrollbar{width:4px}
#session-list::-webkit-scrollbar-track{background:transparent}
#session-list::-webkit-scrollbar-thumb{background:#30363d;border-radius:2px}
/* Progress Bar */
#progress-container{display:none;padding:0 20px;border-bottom:1px solid #30363d;background:#161b22}
#progress-container.visible{display:block}
#progress-bar-wrap{width:100%;height:6px;background:#21262d;border-radius:3px;margin:10px 0;overflow:hidden}
#progress-bar{height:100%;background:linear-gradient(90deg,#238636,#3fb950);border-radius:3px;width:0%;transition:width .3s ease}
#progress-text{font-size:12px;color:#8b949e;margin-bottom:6px;display:flex;justify-content:space-between}
#progress-text .step{color:#c9d1d9}
#progress-text .pct{color:#3fb950;font-weight:600}
/* Inline Question Bubble */
.msg.question{align-self:flex-start;background:linear-gradient(135deg,#1a1f2e,#1c2333);border:1px solid #30363d;border-left:3px solid #d29922;border-bottom-left-radius:4px;animation:slideIn .3s ease}
.msg.question .q-header{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.msg.question .q-icon{width:20px;height:20px;border-radius:50%;background:#d2992233;display:flex;align-items:center;justify-content:center;font-size:12px}
.msg.question .q-title{font-size:12px;color:#d29922;font-weight:600;letter-spacing:.5px;text-transform:uppercase}
.msg.question .q-text{font-size:14px;color:#e6edf3;margin-bottom:12px;line-height:1.5}
.msg.question .q-options{display:flex;flex-wrap:wrap;gap:8px}
.msg.question .q-options button{padding:7px 16px;border-radius:8px;border:1px solid #30363d;background:#21262d;color:#c9d1d9;font-size:13px;cursor:pointer;transition:all .15s ease}
.msg.question .q-options button:hover{background:#d2992233;border-color:#d29922;color:#d29922;transform:translateY(-1px)}
.msg.question .q-options button.selected{background:#d29922;border-color:#d29922;color:#0d1117;font-weight:600}
.msg.question .q-answered{font-size:12px;color:#3fb950;margin-top:8px;display:flex;align-items:center;gap:4px}
.msg.question .q-input-wrap{display:flex;gap:8px;width:100%}
.msg.question .q-input-wrap input{flex:1;padding:7px 12px;border-radius:8px;border:1px solid #30363d;background:#0d1117;color:#c9d1d9;font-size:13px;outline:none;transition:border-color .15s}
.msg.question .q-input-wrap input:focus{border-color:#d29922}
.msg.question .q-input-wrap button{padding:7px 16px;border-radius:8px;border:1px solid #d29922;background:#d2992233;color:#d29922;font-size:13px;cursor:pointer;transition:all .15s}
.msg.question .q-input-wrap button:hover{background:#d29922;color:#0d1117}
@keyframes slideIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
</style>
</head>
<body>
<div id="sidebar">
  <div class="brand">
    <div class="dot"></div>
    <span>Chats</span>
  </div>
  <button class="new-btn" onclick="newSession()">+ New Chat</button>
  <div id="session-list"></div>
</div>
<div id="main">
  <header>
    <h1>AgentScope Chat</h1>
    <span>DeepSeek V4 Pro</span>
  </header>
  <div id="progress-container">
    <div id="progress-text">
      <span class="step">Initializing...</span>
      <span class="pct">0%</span>
    </div>
    <div id="progress-bar-wrap">
      <div id="progress-bar"></div>
    </div>
  </div>
  <div id="chat"></div>
  <footer>
    <input id="input" placeholder="Type a message..." autofocus>
    <button id="send" onclick="send()">Send</button>
    <button id="task-btn" onclick="submitTask()" style="border-color:#30363d;background:#21262d;font-size:12px">Task</button>
  </footer>
</div>
<script>
const chat=document.getElementById('chat');
const input=document.getElementById('input');
const btn=document.getElementById('send');
const sessionList=document.getElementById('session-list');
let busy=false;
let activeSessionId=null;

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

function addToolCard(toolCallId,name,status){
  const d=document.createElement('div');
  d.className='tool-card';
  d.id='tc-'+toolCallId;
  const iconMap={running:'\u25b6',ok:'\u2713',fail:'\u2717',stop:'\u25a0'};
  const icon=iconMap[status]||'\u25b6';
  d.innerHTML='<div class="tc-header" onclick="this.parentElement.classList.toggle(\\'expanded\\')">'+
    '<div class="tc-icon '+status+'">'+icon+'</div>'+
    '<div class="tc-name">'+escapeHtml(name)+'</div>'+
    '<div class="tc-status '+status+'">'+status.toUpperCase()+'</div>'+
    '<div class="tc-chevron">\u25bc</div>'+
    '</div>'+
    '<div class="tc-body"><div class="tc-output"></div></div>';
  chat.appendChild(d);
  chat.scrollTop=chat.scrollHeight;
  return d;
}

function appendToolOutput(toolCallId,text){
  const card=document.getElementById('tc-'+toolCallId);
  if(!card)return;
  const out=card.querySelector('.tc-output');
  if(!out)return;
  if(text==='[binary output]'){
    out.className='tc-output binary';
    out.textContent='[binary data - cannot display]';
  }else{
    out.textContent+=(out.textContent?'\\n':'')+text;
  }
  card.classList.add('expanded');
  chat.scrollTop=chat.scrollHeight;
}

function updateToolStatus(toolCallId,status){
  const card=document.getElementById('tc-'+toolCallId);
  if(!card)return;
  const icon=card.querySelector('.tc-icon');
  const st=card.querySelector('.tc-status');
  const iconMap={ok:'\u2713',fail:'\u2717',stop:'\u25a0'};
  icon.className='tc-icon '+status;
  icon.textContent=iconMap[status]||'\u25a0';
  st.className='tc-status '+status;
  st.textContent=status.toUpperCase();
  // Auto-collapse successful tools after 2s
  if(status==='ok'){
    setTimeout(()=>card.classList.remove('expanded'),2000);
  }
  // Show empty body if no output
  const body=card.querySelector('.tc-body');
  const out=card.querySelector('.tc-output');
  if(out&&!out.textContent.trim()){
    out.className='tc-empty';
    out.textContent='no output';
  }
}

function addDlBtn(parent,path,label){
  const a=document.createElement('a');
  a.className='dl-btn';
  a.href='/api/files/download?path='+encodeURIComponent(path);
  a.download=path.split('/').pop();
  a.textContent='\\u2b07 '+label;
  parent.appendChild(a);
}

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

// ---- Session Management ----

async function loadSessions(){
  try{
    const r=await fetch('/api/sessions');
    const sessions=await r.json();
    sessionList.innerHTML='';
    sessions.forEach(s=>{
      const div=document.createElement('div');
      div.className='item'+(s.id===activeSessionId?' active':'');
      div.innerHTML='<div>'+escapeHtml(s.display_name||('Session '+s.created_at.slice(0,10)))+'</div><div class="time">'+s.created_at.slice(0,16)+'</div>';
      div.onclick=()=>switchSession(s.id);
      sessionList.appendChild(div);
    });
  }catch(e){console.error('loadSessions:',e);}
}

function escapeHtml(text){
  const d=document.createElement('div');
  d.textContent=text;
  return d.innerHTML;
}

async function loadActiveSession(){
  try{
    const r=await fetch('/api/sessions/active');
    if(!r.ok)return;
    const data=await r.json();
    activeSessionId=data.session_id;
    renderHistory(data.messages||[]);
    loadSessions();
  }catch(e){console.error('loadActiveSession:',e);}
}

function renderHistory(messages){
  chat.innerHTML='';
  messages.forEach(msg=>{
    const d=addMsg(msg.role,msg.content);
    if(msg.role==='agent') detectFiles(msg.content,d.querySelector('.content'));
  });
}

async function switchSession(sid){
  if(busy||sid===activeSessionId)return;
  try{
    const r=await fetch('/api/sessions/'+sid+'/switch',{method:'POST'});
    if(!r.ok){alert('Failed to switch session');return;}
    const data=await r.json();
    activeSessionId=data.session_id;
    renderHistory(data.messages||[]);
    loadSessions();
  }catch(e){console.error('switchSession:',e);}
}

async function newSession(){
  if(busy)return;
  try{
    const r=await fetch('/api/sessions/new',{method:'POST'});
    if(!r.ok){alert('Failed to create session');return;}
    const data=await r.json();
    activeSessionId=data.session_id;
    chat.innerHTML='';
    loadSessions();
  }catch(e){console.error('newSession:',e);}
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
          addToolCard(d.tool_call_id,d.name,'running');
        }else if(d.type==='tool_result'){
          updateToolStatus(d.tool_call_id,d.status.replace('[','').replace(']','').toLowerCase());
        }else if(d.type==='tool_output'){
          appendToolOutput(d.tool_call_id,d.text);
        }
      }
      chat.scrollTop=chat.scrollHeight;
    }
    renderMd();
    detectFiles(rawText,contentDiv);
    loadSessions();
  }catch(e){
    contentDiv.innerHTML='<span style="color:#ff4444">Error: '+e.message+'</span>';
  }
  busy=false;btn.disabled=false;
  input.focus();
}

// ---- Progress Bar ----

function showProgress(){
  document.getElementById('progress-container').classList.add('visible');
}

function updateProgress(pct,step){
  document.getElementById('progress-bar').style.width=pct+'%';
  document.getElementById('progress-text').querySelector('.step').textContent=step||'Working...';
  document.getElementById('progress-text').querySelector('.pct').textContent=pct+'%';
}

function hideProgress(){
  document.getElementById('progress-container').classList.remove('visible');
  document.getElementById('progress-bar').style.width='0%';
}

// ---- Async Task ----

async function submitTask(){
  const text=input.value.trim();
  if(!text||busy)return;
  busy=true;
  const taskBtn=document.getElementById('task-btn');
  taskBtn.disabled=true;
  btn.disabled=true;
  addMsg('user',text);
  input.value='';

  try{
    const r=await fetch('/api/tasks',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({content:text})
    });
    const data=await r.json();
    const taskId=data.task_id;

    // Connect to SSE for progress
    showProgress();
    updateProgress(0,'Task submitted...');

    const evtSource=new EventSource('/api/tasks/'+taskId+'/stream');
    evtSource.onmessage=function(e){
      const d=JSON.parse(e.data);
      if(d.type==='progress'){
        updateProgress(d.progress,d.current_step||'Working...');
      }else if(d.type==='done'){
        updateProgress(100,'Completed');
        setTimeout(hideProgress,2000);
        addMsg('agent',d.result||'Task completed');
        evtSource.close();
        loadSessions();
      }else if(d.type==='error'){
        updateProgress(0,'Error: '+d.error);
        setTimeout(hideProgress,3000);
        evtSource.close();
      }
    };
    evtSource.onerror=function(){
      evtSource.close();
      hideProgress();
    };
  }catch(e){
    hideProgress();
    addMsg('agent','Error: '+e.message);
  }
  busy=false;
  btn.disabled=false;
  taskBtn.disabled=false;
  input.focus();
}

loadActiveSession();

// ---- Inline Question (Human-in-the-loop) ----

let currentQuestionTaskId=null;
let currentQuestionBubble=null;

async function checkPendingQuestions(){
  try{
    const r=await fetch('/api/tasks/pending-questions');
    if(!r.ok)return;
    const questions=await r.json();
    const keys=Object.keys(questions);
    if(keys.length>0&&!currentQuestionTaskId){
      const taskId=keys[0];
      const q=questions[taskId];
      showInlineQuestion(taskId,q.question,q.options||[]);
    }
  }catch(e){console.error('checkPendingQuestions:',e);}
}

function showInlineQuestion(taskId,question,options){
  currentQuestionTaskId=taskId;
  const d=document.createElement('div');
  d.className='msg question';
  d.id='question-'+taskId;
  let optionsHtml='';
  if(options.length>0){
    optionsHtml='<div class="q-options">'+options.map(o=>
      '<button onclick="selectOption(\\''+taskId+'\\',\\''+escapeHtml(o).replace(/'/g,"\\\\'")+'\\',this)">'+escapeHtml(o)+'</button>'
    ).join('')+'</div>';
  }else{
    optionsHtml='<div class="q-input-wrap">'+
      '<input id="q-input-'+taskId+'" type="text" placeholder="Type your response..." onkeydown="if(event.key===\\'Enter\\')submitTextResponse(\\''+taskId+'\\')">'+
      '<button onclick="submitTextResponse(\\''+taskId+'\\')">Send</button>'+
      '</div>';
  }
  d.innerHTML='<div class="q-header">'+
    '<div class="q-icon">?</div>'+
    '<div class="q-title">Agent needs your input</div>'+
    '</div>'+
    '<div class="q-text">'+escapeHtml(question)+'</div>'+
    optionsHtml;
  chat.appendChild(d);
  chat.scrollTop=chat.scrollHeight;
  currentQuestionBubble=d;
}

function selectOption(taskId,option,btn){
  // Mark selected, disable all buttons
  const d=document.getElementById('question-'+taskId);
  if(!d)return;
  const buttons=d.querySelectorAll('.q-options button');
  buttons.forEach(b=>{b.disabled=true;b.classList.remove('selected')});
  if(btn&&btn.target)btn.target.classList.add('selected');
  respondToQuestion(taskId,option);
}

async function submitTextResponse(taskId){
  const inp=document.getElementById('q-input-'+taskId);
  if(!inp||!inp.value.trim())return;
  respondToQuestion(taskId,inp.value.trim());
}

async function respondToQuestion(taskId,response){
  try{
    await fetch('/api/tasks/'+encodeURIComponent(taskId)+'/respond',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({response:response})
    });
    // Mark question as answered
    const d=document.getElementById('question-'+taskId);
    if(d){
      const opts=d.querySelector('.q-options');
      const inp=d.querySelector('.q-input-wrap');
      if(opts)opts.style.display='none';
      if(inp)inp.style.display='none';
      const answered=document.createElement('div');
      answered.className='q-answered';
      answered.innerHTML='&#10003; Answered: '+escapeHtml(response);
      d.appendChild(answered);
    }
    currentQuestionTaskId=null;
    currentQuestionBubble=null;
  }catch(e){console.error('respondToQuestion:',e);}
}

setInterval(checkPendingQuestions,5000);
</script>
</body>
</html>"""


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
            # Use active session (persisted across restarts)
            session_id = getattr(agent, "_active_session_id", None)
            if not session_id:
                session_id = store.create_session(name="web-chat") if store else ""
                if store:
                    pass  # active_session already written on startup
                object.__setattr__(agent, "_active_session_id", session_id)

            # Persist user message
            if store and session_id:
                store.save_message(session_id, "user", content)

            _last_summary: str | None = agent.state.summary
            full_reply = ""
            # Track active tool calls for grouping
            tool_call_names: dict[str, str] = {}
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
                    full_reply += evt.delta
                    yield _sse({"type": "text", "text": evt.delta})
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