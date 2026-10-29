/**
 * Freestyle-02 Scenario Builder — Client-side Logic
 * SSE streaming, chat, gates, Q&A, file browser, consistency reports
 */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let sessionId = null;
let eventSource = null;
let selectedModel = '';      // '', 'sonnet', 'haiku'
let selectedEffort = 'high'; // low, medium, high, xhigh, max
let selectedUiLang = 'ru';   // language for AI communication
let selectedScLang = 'ru';   // language for scenario content
const EFFORT_VALUES = ['low', 'medium', 'high', 'xhigh', 'max'];

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  $('#btn-new-session').addEventListener('click', createSession);
  $('#btn-open-scenario').addEventListener('click', openExistingScenario);
  $('#btn-send').addEventListener('click', sendMessage);
  $('#btn-upload').addEventListener('click', () => $('#file-input').click());
  $('#file-input').addEventListener('change', handleFileUpload);
  $('#chat-input').addEventListener('input', autoResize);
  $('#chat-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  $('#scenario-select').addEventListener('change', (e) => {
    $('#btn-open-scenario').disabled = !e.target.value;
  });
  $('.modal__backdrop')?.addEventListener('click', closeFileModal);

  // Model selection buttons (welcome screen)
  $$('#model-options .model-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('#model-options .model-btn').forEach(b => b.classList.remove('model-btn--active'));
      btn.classList.add('model-btn--active');
      selectedModel = btn.dataset.model;
    });
  });

  // Effort slider (welcome screen)
  const effortSlider = $('#effort-slider');
  if (effortSlider) {
    effortSlider.addEventListener('input', () => {
      selectedEffort = EFFORT_VALUES[effortSlider.value];
    });
  }

  // Top-bar settings dropdowns (in-session changes)
  $('#model-select-bar')?.addEventListener('change', (e) => updateSettings({ model_id: e.target.value }));
  $('#effort-select-bar')?.addEventListener('change', (e) => updateSettings({ effort: e.target.value }));
  $('#ui-lang-bar')?.addEventListener('change', (e) => updateSettings({ ui_language: e.target.value }));
  $('#sc-lang-bar')?.addEventListener('change', (e) => updateSettings({ scenario_language: e.target.value }));

  // Welcome screen language selectors
  $('#ui-lang-select')?.addEventListener('change', (e) => { selectedUiLang = e.target.value; });
  $('#sc-lang-select')?.addEventListener('change', (e) => { selectedScLang = e.target.value; });

  // Load existing scenarios into dropdown
  loadScenarios();
});

// ---------------------------------------------------------------------------
// Session management
// ---------------------------------------------------------------------------
async function createSession() {
  try {
    const res = await fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_files: [], workspace_dir: '',
        model_id: selectedModel, effort: selectedEffort,
        ui_language: selectedUiLang, scenario_language: selectedScLang,
        fork: false,
      }),
    });
    const data = await res.json();
    sessionId = data.session_id;
    showChatUI();
    syncSettingsBar(data);
    connectSSE();
    const modelLabel = selectedModel || 'Auto';
    addSystemMessage(`New session created (model: ${modelLabel}, effort: ${selectedEffort}). Upload source files and describe your scenario.`);
  } catch (err) {
    console.error('Failed to create session:', err);
  }
}

async function openExistingScenario() {
  const select = $('#scenario-select');
  const scenarioPath = select.value;
  if (!scenarioPath) return;

  const scenarioName = select.options[select.selectedIndex].text;

  // Show fork dialog
  const forkName = await showForkDialog(scenarioName);
  if (forkName === null) return; // user cancelled

  try {
    const res = await fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scenario_path: scenarioPath,
        fork: true,
        fork_name: forkName,
        model_id: selectedModel, effort: selectedEffort,
        ui_language: selectedUiLang, scenario_language: selectedScLang,
      }),
    });
    if (!res.ok) {
      const err = await res.json();
      addSystemMessage(`Error: ${err.detail || 'Unknown error'}`);
      return;
    }
    const data = await res.json();
    sessionId = data.session_id;
    showChatUI();
    syncSettingsBar(data);
    connectSSE();
    refreshFiles();
    const modelLabel = selectedModel || 'Auto';
    if (data.forked_from) {
      addSystemMessage(`📂 Forked: ${data.forked_from} → ${data.fork_name}`);
    }
    addSystemMessage(`📂 Workspace: ${data.workspace_dir} (model: ${modelLabel}, effort: ${selectedEffort})`);
    addSystemMessage(`Loaded ${data.source_files_loaded} files. Describe what you want to do with this scenario.`);
  } catch (err) {
    console.error('Failed to open scenario:', err);
  }
}

function showForkDialog(scenarioName) {
  return new Promise((resolve) => {
    // Build a simple inline dialog
    const overlay = document.createElement('div');
    overlay.className = 'fork-dialog-overlay';
    overlay.innerHTML = `
      <div class="fork-dialog">
        <div class="fork-dialog__title">📋 Fork Scenario</div>
        <div class="fork-dialog__desc">
          Original <strong>${escHtml(scenarioName)}</strong> will remain unchanged.<br>
          A copy will be created for editing.
        </div>
        <div class="fork-dialog__input-wrap">
          <label>Fork name (leave empty for auto):</label>
          <input type="text" class="fork-dialog__input" placeholder="Auto-generated" id="fork-name-input">
        </div>
        <div class="fork-dialog__actions">
          <button class="btn btn--primary" id="fork-confirm">Fork & Open</button>
          <button class="btn btn--ghost" id="fork-cancel">Cancel</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const input = overlay.querySelector('#fork-name-input');
    input.focus();

    const cleanup = (val) => {
      overlay.remove();
      resolve(val);
    };

    overlay.querySelector('#fork-confirm').addEventListener('click', () => cleanup(input.value.trim()));
    overlay.querySelector('#fork-cancel').addEventListener('click', () => cleanup(null));
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') cleanup(input.value.trim());
      if (e.key === 'Escape') cleanup(null);
    });
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) cleanup(null);
    });
  });
}

async function loadScenarios() {
  const select = $('#scenario-select');
  try {
    const res = await fetch('/api/scenarios');
    const data = await res.json();
    select.innerHTML = '<option value="">— Select a scenario —</option>';

    if (!data.scenarios || data.scenarios.length === 0) {
      select.innerHTML += '<option value="" disabled>No scenarios found</option>';
      return;
    }

    // Group by project
    const groups = {};
    data.scenarios.forEach(s => {
      if (!groups[s.group]) groups[s.group] = [];
      groups[s.group].push(s);
    });

    for (const [group, scenarios] of Object.entries(groups)) {
      const optgroup = document.createElement('optgroup');
      optgroup.label = group;
      scenarios.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.path;
        opt.textContent = `${s.name}  (${s.components} files)`;
        optgroup.appendChild(opt);
      });
      select.appendChild(optgroup);
    }
  } catch (err) {
    select.innerHTML = '<option value="" disabled>Error loading scenarios</option>';
    console.error('Failed to load scenarios:', err);
  }
}

function showChatUI() {
  $('#welcome-screen').classList.add('hidden');
  $('#chat-messages').classList.remove('hidden');
  $('#chat-input-area').classList.remove('hidden');
  $('#btn-send').disabled = false;
  // Show the settings bar in top-bar
  $('#model-settings-bar')?.classList.remove('hidden');
}

function syncSettingsBar(data) {
  // Sync the top-bar dropdowns with current session settings
  const modelBar = $('#model-select-bar');
  const effortBar = $('#effort-select-bar');
  const uiLangBar = $('#ui-lang-bar');
  const scLangBar = $('#sc-lang-bar');
  if (modelBar) modelBar.value = data.model_id || '';
  if (effortBar) effortBar.value = data.effort || 'high';
  if (uiLangBar) uiLangBar.value = data.ui_language || 'ru';
  if (scLangBar) scLangBar.value = data.scenario_language || 'ru';
}

async function updateSettings(settings) {
  if (!sessionId) return;
  try {
    const res = await fetch(`/api/sessions/${sessionId}/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
    if (res.ok) {
      const data = await res.json();
      const modelLabel = data.model_id || 'Auto';
      addSystemMessage(`\u2699\ufe0f Settings updated: model=${modelLabel}, effort=${data.effort}`);
    } else {
      const err = await res.json();
      addSystemMessage(`Settings error: ${err.detail}`);
    }
  } catch (err) {
    addSystemMessage(`Settings error: ${err.message}`);
  }
}

// ---------------------------------------------------------------------------
// SSE Connection
// ---------------------------------------------------------------------------
function connectSSE() {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/api/stream/${sessionId}`);
  eventSource.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data);
      handleSSEEvent(event);
    } catch (err) { console.error('SSE parse error:', err); }
  };
  eventSource.onerror = () => {
    console.warn('SSE disconnected, reconnecting in 3s...');
    setTimeout(() => { if (sessionId) connectSSE(); }, 3000);
  };
}

function handleSSEEvent(event) {
  const { type, data } = event;
  switch (type) {
    case 'message': handleMessage(data); break;
    case 'gate': handleGate(data); break;
    case 'question': handleQuestion(data); break;
    case 'consistency': handleConsistency(data); break;
    case 'step_change': handleStepChange(data); break;
    case 'completed': handleCompleted(data); break;
    case 'ping': break;
    case 'connected': updateStatus('running'); break;
    default: console.log('Unknown event:', type, data);
  }
}

// ---------------------------------------------------------------------------
// Chat Messages
// ---------------------------------------------------------------------------
function sendMessage() {
  const input = $('#chat-input');
  const text = input.value.trim();
  if (!text || !sessionId) return;

  addUserMessage(text);
  input.value = '';
  autoResize.call(input);

  fetch(`/api/sessions/${sessionId}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: text }),
  }).then(res => {
    if (!res.ok) {
      if (res.status === 409) {
        addSystemMessage('⏳ Orchestrator is already running. Wait for it to finish.');
      } else {
        res.json().then(d => addSystemMessage(`Error ${res.status}: ${d.detail || 'Unknown'}`))
             .catch(() => addSystemMessage(`Error: server returned ${res.status}`));
      }
    }
  }).catch(err => addSystemMessage(`Error: ${err.message}`));
}

function handleMessage(data) {
  const { agent, step, text, log_file, full_length } = data;
  const isSystem = agent === 'system';
  const isConsistency = agent === 'ConsistencyChecker';

  if (isSystem) {
    // System messages: show spinner for ⏳, hide for ✅/🤖
    if (text.includes('⏳')) {
      showLoading(text.split('⏳')[1]?.trim().substring(0, 50) || 'Working...');
    } else if (text.includes('✅') || text.includes('🤖')) {
      hideLoading();
    }
    addSystemMessage(text);
    return;
  }

  hideLoading();
  const cls = isConsistency ? 'chat-msg--consistency' : 'chat-msg--agent';
  const agentCls = isConsistency ? 'chat-msg__agent--consistency' : '';

  // Build "View Full" button if this is a truncated long message
  let viewFullBtn = '';
  if (log_file) {
    const sizeLabel = full_length ? `${(full_length / 1024).toFixed(1)}K` : '';
    viewFullBtn = `
      <button class="btn-view-full" onclick="openLogFile('${escAttr(log_file)}')">
        📄 View Full ${sizeLabel}
      </button>
    `;
  }

  const el = document.createElement('div');
  el.className = `chat-msg ${cls}`;
  el.innerHTML = `
    <div class="chat-msg__header">
      <span class="chat-msg__agent ${agentCls}">${escHtml(agent)}</span>
      <span class="chat-msg__step">Step ${step}</span>
      ${viewFullBtn}
    </div>
    <div class="chat-msg__text">${escHtml(text)}</div>
  `;
  appendMessage(el);
  refreshFiles();
}

async function openLogFile(filename) {
  if (!sessionId) return;
  try {
    const res = await fetch(`/api/sessions/${sessionId}/logs/${filename}`);
    if (!res.ok) {
      addSystemMessage(`Error loading log: ${res.status}`);
      return;
    }
    const data = await res.json();
    const modal = $('#file-modal');
    modal.dataset.logFile = filename;
    $('#file-modal-title').textContent = `${data.filename} (${(data.size / 1024).toFixed(1)}K)`;
    $('#file-modal-body').value = data.content;
    $('#file-modal-save').classList.remove('hidden');
    modal.classList.remove('hidden');
    // Track original content for dirty detection
    modal.dataset.originalContent = data.content;
  } catch (err) {
    addSystemMessage(`Error: ${err.message}`);
  }
}

async function saveLogFile() {
  const modal = $('#file-modal');
  const filename = modal.dataset.logFile;
  if (!filename || !sessionId) return;
  const content = $('#file-modal-body').value;
  try {
    const res = await fetch(`/api/sessions/${sessionId}/logs/${filename}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
    if (!res.ok) {
      addSystemMessage(`Error saving: ${res.status}`);
      return;
    }
    modal.dataset.originalContent = content;
    const data = await res.json();
    $('#file-modal-save').textContent = '✅ Saved';
    setTimeout(() => { $('#file-modal-save').textContent = '💾 Save'; }, 2000);
    const fieldInfo = data.state_updated ? ` → state.${data.state_updated} updated` : '';
    addSystemMessage(`💾 Saved edits to ${filename}${fieldInfo}`);
  } catch (err) {
    addSystemMessage(`Error: ${err.message}`);
  }
}

function addUserMessage(text) {
  const el = document.createElement('div');
  el.className = 'chat-msg chat-msg--user';
  el.innerHTML = `<div class="chat-msg__text">${escHtml(text)}</div>`;
  appendMessage(el);
}

function addSystemMessage(text) {
  const el = document.createElement('div');
  el.className = 'chat-msg chat-msg--system';
  el.textContent = text;
  appendMessage(el);
}

function appendMessage(el) {
  const container = $('#chat-messages');
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
}

// ---------------------------------------------------------------------------
// Loading indicator
// ---------------------------------------------------------------------------
let loadingEl = null;
let loadingStart = 0;
let loadingTimer = null;

function showLoading(label) {
  hideLoading();
  loadingStart = Date.now();
  loadingEl = document.createElement('div');
  loadingEl.className = 'chat-loading';
  loadingEl.innerHTML = `
    <div class="chat-loading__spinner"></div>
    <span class="chat-loading__label">${escHtml(label)}</span>
    <span class="chat-loading__time">0s</span>
  `;
  const container = $('#chat-messages');
  container.appendChild(loadingEl);
  container.scrollTop = container.scrollHeight;

  loadingTimer = setInterval(() => {
    if (loadingEl) {
      const elapsed = Math.round((Date.now() - loadingStart) / 1000);
      const timeEl = loadingEl.querySelector('.chat-loading__time');
      if (timeEl) timeEl.textContent = `${elapsed}s`;
    }
  }, 1000);
}

function hideLoading() {
  if (loadingEl) {
    loadingEl.remove();
    loadingEl = null;
  }
  if (loadingTimer) {
    clearInterval(loadingTimer);
    loadingTimer = null;
  }
}

// ---------------------------------------------------------------------------
// Completion summary
// ---------------------------------------------------------------------------
function handleCompleted(data) {
  hideLoading();
  const { status, elapsed_seconds, steps, questions, gates_approved, gates_total, consistency_checks } = data;

  const statusColors = { completed: '#4ade80', failed: '#f87171', paused: '#fbbf24' };
  const statusColor = statusColors[status] || '#94a3b8';
  const minutes = (elapsed_seconds / 60).toFixed(1);

  const el = document.createElement('div');
  el.className = 'chat-msg chat-msg--completion';
  el.innerHTML = `
    <div class="completion-banner" style="border-left: 4px solid ${statusColor}">
      <div class="completion-banner__title" style="color: ${statusColor}">
        ${status === 'completed' ? '✅' : status === 'failed' ? '❌' : '⏸️'} Pipeline ${status.toUpperCase()}
      </div>
      <div class="completion-banner__stats">
        <span>⏱️ ${elapsed_seconds}s (${minutes} min)</span>
        <span>📋 ${steps} steps</span>
        <span>❓ ${questions} questions</span>
        <span>🔒 ${gates_approved}/${gates_total} gates</span>
        <span>🔍 ${consistency_checks} checks</span>
      </div>
    </div>
  `;
  appendMessage(el);

  updateStatus(status);
  refreshFiles();
}

// ---------------------------------------------------------------------------
// Gates
// ---------------------------------------------------------------------------
function handleGate(data) {
  const { gate_id, description, status } = data;
  updateStatus('waiting_for_approval');

  const list = $('#gates-list');
  if (list.querySelector('.gates-list__empty')) list.innerHTML = '';

  const existing = list.querySelector(`[data-gate="${gate_id}"]`);
  if (existing) existing.remove();

  const card = document.createElement('div');
  card.className = 'gate-card';
  card.dataset.gate = gate_id;
  card.dataset.status = status;
  card.innerHTML = `
    <div class="gate-card__header">
      <span class="gate-card__id">Gate ${gate_id}</span>
      <span class="gate-card__status">${status}</span>
    </div>
    <div class="gate-card__desc">${escHtml(description)}</div>
    <textarea class="gate-card__comment" id="gate-comment-${gate_id}" 
      placeholder="Required for Reject: describe what to fix..." rows="2"></textarea>
    <div class="gate-card__actions">
      <button class="btn btn--sm btn--approve" onclick="approveGate(${gate_id}, true)">✓ Approve</button>
      <button class="btn btn--sm btn--reject" onclick="approveGate(${gate_id}, false)">✗ Reject & Fix</button>
    </div>
  `;
  list.appendChild(card);
  addSystemMessage(`🔒 Gate ${gate_id}: ${description} — awaiting your approval`);
}

async function approveGate(gateId, approved) {
  const commentEl = $(`#gate-comment-${gateId}`);
  const comment = commentEl ? commentEl.value.trim() : '';

  // Reject requires a comment — ContentWriter needs instructions
  if (!approved && !comment) {
    commentEl.style.borderColor = 'var(--accent-red)';
    commentEl.placeholder = '⚠️ Required: describe what needs to be fixed!';
    commentEl.focus();
    addSystemMessage('⚠️ Please describe what to fix before rejecting');
    return;
  }

  try {
    await fetch(`/api/gates/${sessionId}/${gateId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved, comment }),
    });
    const card = $(`[data-gate="${gateId}"]`);
    if (card) {
      card.dataset.status = approved ? 'approved' : 'rejected';
      card.querySelector('.gate-card__status').textContent = approved ? 'approved' : 'rejected';
      const commentText = comment ? ` — "${comment}"` : '';
      card.querySelector('.gate-card__actions').innerHTML =
        `<span style="font-size:12px;color:var(${approved ? '--accent-green' : '--accent-red'})">${approved ? '✓ Approved' : '✗ Rejected'}${escHtml(commentText)}</span>`;
    }
    const commentMsg = comment ? ` (${comment})` : '';
    addSystemMessage(approved ? `✓ Gate ${gateId} approved${commentMsg}` : `✗ Gate ${gateId} rejected${commentMsg}`);
    if (approved) updateStatus('running');
  } catch (err) { addSystemMessage(`Error: ${err.message}`); }
}

// ---------------------------------------------------------------------------
// Questions
// ---------------------------------------------------------------------------
function handleQuestion(data) {
  const { question_id, agent, question, context, options } = data;
  updateStatus('waiting_for_user');

  // Truncate long question text
  const isLong = question.length > 300;
  const displayQ = isLong ? question.substring(0, 200) + '...' : question;

  let optionsHtml = '';
  if (options && options.length > 0) {
    optionsHtml = `<div class="question-card__options">${options.map(o =>
      `<button class="question-card__option" onclick="answerQuestionOption('${question_id}', '${escAttr(o)}')">${escHtml(o)}</button>`
    ).join('')}</div>`;
  }

  let expandBtn = '';
  if (isLong) {
    expandBtn = `<button class="btn-view-full" onclick="showFullQuestion(this)">📄 View Full ${(question.length/1024).toFixed(1)}K</button>`;
  }

  const el = document.createElement('div');
  el.className = 'chat-msg chat-msg--question';
  el.dataset.questionId = question_id;
  el.innerHTML = `
    <div class="chat-msg__header">
      <span class="chat-msg__agent">❓ ${escHtml(agent)}</span>
      ${expandBtn}
    </div>
    <div class="chat-msg__text">${escHtml(displayQ)}</div>
    ${isLong ? `<div class="question-card__full hidden">${escHtml(question)}</div>` : ''}
    ${context ? `<div class="question-card__context">${escHtml(context)}</div>` : ''}
    ${optionsHtml}
    <div class="question-card__input-wrap">
      <input class="question-card__input" placeholder="Your answer..." id="q-input-${question_id}">
      <button class="btn btn--sm btn--primary" onclick="answerQuestionText('${question_id}')">Send</button>
    </div>
  `;
  appendMessage(el);

  const inputEl = el.querySelector('.question-card__input');
  inputEl.focus();
  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') answerQuestionText(question_id);
  });
}

async function showFullQuestion(btn) {
  const card = btn.closest('.chat-msg--question');
  if (!card) return;
  const full = card.querySelector('.question-card__full');
  if (!full) return;
  if (!sessionId) return;

  const content = full.textContent;
  const qid = card.dataset.questionId || 'unknown';

  // Save content as a log file so it can be edited and saved back
  try {
    const res = await fetch(`/api/sessions/${sessionId}/save-question-log`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question_id: qid, content }),
    });
    if (res.ok) {
      const data = await res.json();
      // Open via the standard editable log viewer
      await openLogFile(data.filename);
      return;
    }
  } catch (err) {
    console.error('Failed to save question log:', err);
  }

  // Fallback: open read-only
  const modal = $('#file-modal');
  modal.dataset.logFile = '';
  $('#file-modal-title').textContent = 'Full Question';
  $('#file-modal-body').value = content;
  $('#file-modal-save').classList.add('hidden');
  modal.classList.remove('hidden');
}

async function answerQuestionText(questionId) {
  const input = $(`#q-input-${questionId}`);
  if (!input) return;
  const answer = input.value.trim();
  if (!answer) return;
  await submitAnswer(questionId, answer);
}

async function answerQuestionOption(questionId, option) {
  await submitAnswer(questionId, option);
}

async function submitAnswer(questionId, answer) {
  try {
    await fetch(`/api/questions/${sessionId}/${questionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer }),
    });
    const card = $(`[data-question-id="${questionId}"]`);
    if (card) {
      const inputWrap = card.querySelector('.question-card__input-wrap');
      if (inputWrap) inputWrap.remove();
      const opts = card.querySelector('.question-card__options');
      if (opts) opts.remove();
      const answerEl = document.createElement('div');
      answerEl.className = 'chat-msg__answer';
      answerEl.innerHTML = `<span class="chat-msg__answer-label">\u2705 Answer:</span> ${escHtml(answer)}`;
      card.appendChild(answerEl);
      card.style.borderColor = 'var(--border)';
      card.style.opacity = '0.85';
    }
    updateStatus('running');
  } catch (err) { addSystemMessage(`Error: ${err.message}`); }
}

// ---------------------------------------------------------------------------
// Consistency
// ---------------------------------------------------------------------------
function handleConsistency(data) {
  const { step, status } = data;
  const list = $('#consistency-list');
  if (list.querySelector('.consistency-list__empty')) list.innerHTML = '';

  const icon = status === 'ok' ? '✅' : status === 'warning' ? '⚠️' : '❌';
  const item = document.createElement('div');
  item.className = 'consistency-item';
  item.dataset.status = status;
  item.textContent = `${icon} Step ${step}: ${status}`;
  list.appendChild(item);
}

// ---------------------------------------------------------------------------
// Step progress
// ---------------------------------------------------------------------------
function handleStepChange(data) {
  const { step, agent } = data;
  const pct = Math.round((step / 10) * 100);
  $('#step-progress-fill').style.width = `${pct}%`;
  $('#step-label').textContent = `Step ${step}/10`;

  const badge = $('#agent-badge');
  badge.classList.remove('hidden');
  $('#agent-name').textContent = agent;

  updateStatus('running');
}

function updateStatus(status) {
  const badge = $('#status-badge');
  badge.dataset.status = status;
  const labels = {
    idle: 'Idle', running: 'Running', waiting_for_user: 'Waiting', waiting_for_approval: 'Approval Needed',
    completed: 'Done', failed: 'Error', paused: 'Paused',
  };
  $('#status-text').textContent = labels[status] || status;

  // Show/hide stop button based on running state
  const stopBtn = $('#btn-stop');
  if (stopBtn) {
    const isActive = ['running', 'waiting_for_user', 'waiting_for_approval'].includes(status);
    stopBtn.classList.toggle('hidden', !isActive);
  }
}

async function stopPipeline() {
  if (!sessionId) return;
  try {
    await fetch(`/api/sessions/${sessionId}/stop`, { method: 'POST' });
    hideLoading();
    addSystemMessage('⏸️ Pipeline stopped by user');
    updateStatus('paused');
  } catch (err) {
    addSystemMessage(`Stop error: ${err.message}`);
  }
}

// ---------------------------------------------------------------------------
// File browser
// ---------------------------------------------------------------------------
async function refreshFiles() {
  if (!sessionId) return;
  try {
    const res = await fetch(`/api/sessions/${sessionId}/files`);
    const data = await res.json();
    const sourceList = $('#source-files-list');
    const genList = $('#generated-files-list');
    sourceList.innerHTML = '';
    genList.innerHTML = '';

    if (!data.files || data.files.length === 0) {
      sourceList.innerHTML = '<div class="file-list__empty">No files</div>';
      genList.innerHTML = '<div class="file-list__empty">No artifacts yet</div>';
      return;
    }

    data.files.forEach(f => {
      const isSource = f.path.startsWith('sources/');
      const target = isSource ? sourceList : genList;
      const item = document.createElement('div');
      item.className = 'file-item';
      item.onclick = () => openFile(f.path);
      item.innerHTML = `
        <span class="file-item__icon">${isSource ? '📋' : '📄'}</span>
        <span class="file-item__name">${escHtml(f.name)}</span>
        <span class="file-item__size">${formatBytes(f.size)}</span>
      `;
      target.appendChild(item);
    });

    if (!sourceList.children.length) sourceList.innerHTML = '<div class="file-list__empty">No source files</div>';
    if (!genList.children.length) genList.innerHTML = '<div class="file-list__empty">No artifacts yet</div>';
  } catch (err) { console.error('Failed to refresh files:', err); }
}

async function openFile(path) {
  try {
    const res = await fetch(`/api/sessions/${sessionId}/files/${path}`);
    const data = await res.json();
    const modal = $('#file-modal');
    modal.dataset.logFile = '';
    $('#file-modal-title').textContent = path;
    $('#file-modal-body').value = data.content;
    $('#file-modal-save').classList.add('hidden');
    modal.classList.remove('hidden');
  } catch (err) { addSystemMessage(`Error reading file: ${err.message}`); }
}

function closeFileModal() {
  const modal = $('#file-modal');
  modal.classList.add('hidden');
  modal.dataset.logFile = '';
  $('#file-modal-save').classList.add('hidden');
}

// ---------------------------------------------------------------------------
// File upload
// ---------------------------------------------------------------------------
async function handleFileUpload(e) {
  if (!sessionId || !e.target.files.length) return;
  for (const file of e.target.files) {
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await fetch(`/api/sessions/${sessionId}/upload`, { method: 'POST', body: form });
      const data = await res.json();
      addSystemMessage(`📎 Uploaded: ${data.uploaded}`);
      refreshFiles();
    } catch (err) { addSystemMessage(`Upload error: ${err.message}`); }
  }
  e.target.value = '';
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function escHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function escAttr(s) { return s.replace(/'/g, "\\'").replace(/"/g, '&quot;'); }
function formatBytes(b) { if (b < 1024) return b + 'B'; if (b < 1048576) return (b/1024).toFixed(1) + 'K'; return (b/1048576).toFixed(1) + 'M'; }
function autoResize() { this.style.height = 'auto'; this.style.height = Math.min(this.scrollHeight, 150) + 'px'; }
