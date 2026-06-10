/* n8nkali dashboard client */

const socket = io();
let activeAgent = 'kali';
let chatHistory = {};   // keyed by agent
let isStreaming = false;

const AGENT_AVATARS = {
  kali:  '🤖', scout: '🔍', forge: '✍️', pixel: '🎨', apex: '✅', user: '👤'
};
const AGENT_NAMES = {
  kali: 'Kali', scout: 'Scout', forge: 'Forge', pixel: 'Pixel', apex: 'Apex'
};

// ── Socket events ──────────────────────────────────────────────────────────────

socket.on('connect', () => {
  setStatus('Connected to dashboard', false);
});

socket.on('disconnect', () => {
  setStatus('Disconnected — reconnecting…', true);
});

socket.on('health_update', (data) => {
  if (data.ok !== undefined) {
    // Direct ollama health check
    updateDot('svc-ollama', data.ok);
  } else {
    updateDot('svc-ollama',  data.ollama?.ok);
    updateDot('svc-scraper', data.scraper?.ok);
    updateDot('svc-n8n',     data.n8n?.ok);
  }
  fetchDbHealth();
});

socket.on('stats_update', (data) => {
  renderQC(data.qc_summary || []);
  renderRuns(data.recent_runs || []);
  const count = data.queue_count || 0;
  document.getElementById('queue-count').textContent = `${count} ready`;
});

socket.on('chat_start', ({ agent }) => {
  isStreaming = true;
  addStreamingMsg(agent);
  setStatus(`${AGENT_NAMES[agent] || agent} is thinking…`, true);
  document.getElementById('btn-send').disabled = true;
  document.getElementById('chat-input').disabled = true;
});

socket.on('chat_token', ({ agent, token }) => {
  appendToken(agent, token);
});

socket.on('chat_done', ({ agent, response }) => {
  finaliseStream(agent, response);
  isStreaming = false;
  setStatus('', false);
  document.getElementById('btn-send').disabled = false;
  document.getElementById('chat-input').disabled = false;
  document.getElementById('chat-input').focus();

  if (!chatHistory[agent]) chatHistory[agent] = [];
  chatHistory[agent].push({ role: 'assistant', content: response });
});

socket.on('chat_error', ({ agent, error }) => {
  appendError(error);
  isStreaming = false;
  setStatus('', false);
  document.getElementById('btn-send').disabled = false;
  document.getElementById('chat-input').disabled = false;
});

// ── Chat functions ─────────────────────────────────────────────────────────────

function switchAgent(agentKey) {
  activeAgent = agentKey;
  document.querySelectorAll('.agent-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.agent === agentKey);
  });
  document.getElementById('active-agent-name').textContent = AGENT_NAMES[agentKey] || agentKey;
  document.getElementById('chat-input').placeholder = `Message ${AGENT_NAMES[agentKey] || agentKey}…`;

  const chatWindow = document.getElementById('chat-window');
  // Clear and re-render this agent's history
  chatWindow.innerHTML = '';
  const hist = chatHistory[agentKey] || [];
  if (hist.length === 0) {
    chatWindow.innerHTML = `
      <div class="chat-welcome">
        <div class="welcome-icon">${AGENT_AVATARS[agentKey] || '🤖'}</div>
        <h2>${AGENT_NAMES[agentKey] || agentKey}</h2>
        <p>Start a conversation with this agent.</p>
      </div>`;
  } else {
    hist.forEach(m => appendMsg(m.role === 'user' ? 'user' : agentKey, m.content));
  }
}

function sendMessage() {
  if (isStreaming) return;
  const input = document.getElementById('chat-input');
  const msg = input.value.trim();
  if (!msg) return;

  input.value = '';
  autoResize(input);

  appendMsg('user', msg);

  if (!chatHistory[activeAgent]) chatHistory[activeAgent] = [];
  chatHistory[activeAgent].push({ role: 'user', content: msg });

  socket.emit('chat', {
    agent: activeAgent,
    message: msg,
    history: chatHistory[activeAgent].slice(-20),
  });
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  } else {
    setTimeout(() => autoResize(e.target), 0);
  }
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

// ── Message rendering ──────────────────────────────────────────────────────────

function appendMsg(sender, content) {
  const chatWindow = document.getElementById('chat-window');
  const welcome = chatWindow.querySelector('.chat-welcome');
  if (welcome) welcome.remove();

  const isUser = sender === 'user';
  const div = document.createElement('div');
  div.className = `msg ${isUser ? 'user' : 'agent'}`;
  div.innerHTML = `
    <div class="msg-avatar">${isUser ? AGENT_AVATARS.user : (AGENT_AVATARS[sender] || '🤖')}</div>
    <div class="msg-body">
      <div class="msg-name">${isUser ? 'You' : (AGENT_NAMES[sender] || sender)}</div>
      <div class="msg-content">${escapeHtml(content)}</div>
    </div>`;
  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  return div;
}

let streamEl = null;

function addStreamingMsg(agent) {
  const chatWindow = document.getElementById('chat-window');
  const welcome = chatWindow.querySelector('.chat-welcome');
  if (welcome) welcome.remove();

  streamEl = document.createElement('div');
  streamEl.className = 'msg agent msg-streaming';
  streamEl.innerHTML = `
    <div class="msg-avatar">${AGENT_AVATARS[agent] || '🤖'}</div>
    <div class="msg-body">
      <div class="msg-name">${AGENT_NAMES[agent] || agent}</div>
      <div class="msg-content" id="stream-content"></div>
    </div>`;
  chatWindow.appendChild(streamEl);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function appendToken(agent, token) {
  const el = document.getElementById('stream-content');
  if (el) {
    el.textContent += token;
    const chatWindow = document.getElementById('chat-window');
    chatWindow.scrollTop = chatWindow.scrollHeight;
  }
}

function finaliseStream(agent, fullText) {
  if (streamEl) {
    streamEl.classList.remove('msg-streaming');
    const content = streamEl.querySelector('.msg-content');
    if (content) content.textContent = fullText;
    streamEl = null;
  }
}

function appendError(msg) {
  const chatWindow = document.getElementById('chat-window');
  const div = document.createElement('div');
  div.style.cssText = 'color:#ef4444;font-size:12px;padding:8px;text-align:center;';
  div.textContent = `Error: ${msg}`;
  chatWindow.appendChild(div);
}

// ── Pipeline controls ──────────────────────────────────────────────────────────

function runPipeline() {
  const cat = document.getElementById('run-category').value;
  const categories = cat === 'all'
    ? ['ebook', 'workbook', 'thumbnail', 'logo', 'coaching']
    : [cat];

  fetch('/api/pipeline/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ categories }),
  })
  .then(r => r.json())
  .then(data => {
    if (data.triggered) {
      showToast(`Pipeline started for: ${categories.join(', ')}`);
    } else {
      showToast(`Failed to start pipeline: ${data.error || 'unknown error'}`);
    }
  })
  .catch(e => showToast(`Error: ${e.message}`));
}

function filterProducts(btn, status) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  fetchProducts(status);
}

// ── Data fetching ──────────────────────────────────────────────────────────────

function fetchHealth() {
  fetch('/api/health')
    .then(r => r.json())
    .then(data => {
      updateDot('svc-ollama',  data.ollama?.ok);
      updateDot('svc-scraper', data.scraper?.ok);
      updateDot('svc-n8n',     data.n8n?.ok);
      updateDot('svc-db',      data.database?.ok);
    })
    .catch(() => {});
}

function fetchDbHealth() {
  fetch('/api/health')
    .then(r => r.json())
    .then(data => updateDot('svc-db', data.database?.ok))
    .catch(() => {});
}

function fetchStats() {
  fetch('/api/pipeline/stats')
    .then(r => r.json())
    .then(data => {
      renderQC(data.qc_summary || []);
      renderRuns(data.recent_runs || []);
      const count = data.queue_count || 0;
      document.getElementById('queue-count').textContent = `${count} ready`;
      updateStageBadges(data.runs || []);
    })
    .catch(() => {});
}

function fetchProducts(status = '') {
  const url = status ? `/api/pipeline/products?status=${status}` : '/api/pipeline/products';
  fetch(url)
    .then(r => r.json())
    .then(data => renderProducts(data))
    .catch(() => {});
}

// ── Rendering ─────────────────────────────────────────────────────────────────

function updateDot(id, ok) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle('ok', !!ok);
  el.classList.toggle('err', ok === false);
}

function renderQC(summary) {
  let pass = 0, revise = 0, reject = 0;
  summary.forEach(row => {
    if (row.decision === 'PASS') pass = row.count;
    if (row.decision === 'NEEDS_REVISION') revise = row.count;
    if (row.decision === 'REJECT') reject = row.count;
  });
  document.getElementById('qc-pass').textContent = pass;
  document.getElementById('qc-revise').textContent = revise;
  document.getElementById('qc-reject').textContent = reject;
}

function renderRuns(runs) {
  const el = document.getElementById('run-list');
  if (!runs || runs.length === 0) {
    el.innerHTML = '<div class="run-empty">No runs yet</div>';
    return;
  }
  el.innerHTML = runs.map(r => `
    <div class="run-item">
      <div class="run-header">
        <span class="run-stage">${r.stage || '—'}</span>
        <span class="run-status ${r.status}">${r.status}</span>
      </div>
      <div class="run-cat">${r.category || '—'}</div>
      <div class="run-time">${formatTime(r.started_at)}</div>
    </div>`).join('');
}

function renderProducts(products) {
  const el = document.getElementById('product-list');
  if (!products || products.length === 0) {
    el.innerHTML = '<div class="product-empty">No products found</div>';
    return;
  }
  el.innerHTML = products.map(p => `
    <div class="product-card">
      <div class="product-header">
        <span class="product-title">${escapeHtml(p.title || 'Untitled')}</span>
        <span class="product-type">${p.product_type || '?'}</span>
      </div>
      <div class="product-status ${p.status}">${p.status?.toUpperCase()}</div>
      <div class="product-time">${formatTime(p.updated_at)}</div>
    </div>`).join('');
}

function updateStageBadges(runs) {
  const stageMap = { research: 0, create: 0, edit: 0, qc: 0 };
  const statusMap = {};
  runs.forEach(r => {
    if (!statusMap[r.stage]) statusMap[r.stage] = r.status;
  });
  ['research', 'create', 'edit', 'qc'].forEach(stage => {
    const badge = document.getElementById(`badge-${stage}`);
    if (!badge) return;
    const status = statusMap[stage];
    if (!status) { badge.textContent = '—'; badge.className = 'stage-badge'; return; }
    badge.textContent = status;
    badge.className = `stage-badge ${status}`;
  });
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function setStatus(msg, thinking) {
  const el = document.getElementById('chat-status');
  el.textContent = msg;
  el.className = `chat-status${thinking ? ' thinking' : ''}`;
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3000);
}

function formatTime(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch { return iso; }
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  fetchHealth();
  fetchStats();
  fetchProducts();

  // Refresh data every 30s
  setInterval(() => {
    fetchStats();
    fetchProducts(document.querySelector('.filter-btn.active')?.dataset?.status || '');
  }, 30000);
});
