const chat=document.getElementById('chat');
const input=document.getElementById('input');
const btn=document.getElementById('send');
const sessionList=document.getElementById('session-list');
let busy=false;
let activeSessionId=null;

input.addEventListener('keydown',e=>{if(e.key==='Enter')send()});

function addMsg(role,text){
  const d=document.createElement('div');
  // Map backend "assistant" role to "agent" CSS class
  const cssRole=role==='assistant'?'agent':role;
  d.className='msg '+cssRole;
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
  const iconMap={running:'▶',ok:'✓',fail:'✗',stop:'■'};
  const icon=iconMap[status]||'▶';
  d.innerHTML='<div class="tc-header" onclick="this.parentElement.classList.toggle(\'expanded\')">'+
    '<div class="tc-icon '+status+'">'+icon+'</div>'+
    '<div class="tc-name">'+escapeHtml(name)+'</div>'+
    '<div class="tc-status '+status+'">'+status.toUpperCase()+'</div>'+
    '<div class="tc-chevron">▼</div>'+
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
    out.textContent+=(out.textContent?'\n':'')+text;
  }
  card.classList.add('expanded');
  chat.scrollTop=chat.scrollHeight;
}

function updateToolStatus(toolCallId,status){
  const card=document.getElementById('tc-'+toolCallId);
  if(!card)return;
  const icon=card.querySelector('.tc-icon');
  const st=card.querySelector('.tc-status');
  const iconMap={ok:'✓',fail:'✗',stop:'■'};
  icon.className='tc-icon '+status;
  icon.textContent=iconMap[status]||'■';
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

function addCompactionNotice(status){
  const label=status==='compacting'?'History Chats Compacting':'History Chats Compacted';
  // Update existing compacting notice if present
  if(status==='completed'){
    const existing=chat.querySelector('.compaction-notice .cn-text');
    if(existing){existing.textContent=label;return;}
  }
  const d=document.createElement('div');
  d.className='compaction-notice';
  d.innerHTML='<div class="cn-line"></div><div class="cn-text">'+label+'</div><div class="cn-line"></div>';
  chat.appendChild(d);
  chat.scrollTop=chat.scrollHeight;
}

function addDlBtn(parent,path,label){
  const a=document.createElement('a');
  a.className='dl-btn';
  a.href='/api/files/download?path='+encodeURIComponent(path);
  a.download=path.split('/').pop();
  a.textContent='⬇ '+label;
  parent.appendChild(a);
}

function detectFiles(text,parent){
  const re=/\b([\/]\S+?\.\w+)/g;
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
    if(msg.role==='agent'||msg.role==='assistant') detectFiles(msg.content,d.querySelector('.content'));
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
      const lines=buffer.split('\n');
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
        }else if(d.type==='compaction'){
          addCompactionNotice(d.status);
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
      '<button onclick="selectOption(\''+taskId+'\',\''+escapeHtml(o).replace(/'/g,"\\'")+'\',this)">'+escapeHtml(o)+'</button>'
    ).join('')+'</div>';
  }else{
    optionsHtml='<div class="q-input-wrap">'+
      '<input id="q-input-'+taskId+'" type="text" placeholder="Type your response..." onkeydown="if(event.key===\'Enter\')submitTextResponse(\''+taskId+'\')">'+
      '<button onclick="submitTextResponse(\''+taskId+'\')">Send</button>'+
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