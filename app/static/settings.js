/* SentinelIQ control room - settings with tabs, source management, tunables. */

const KEY_A = ['model_conf', 'model_imgsz', 'frame_skip', 'faint_seconds', 'msg_cooldown'];
const KEY_B = ['item_detector', 'audio_enabled', 'manual_armed', 'schedule_enabled'];
const KEY_C = ['telegram_token', 'telegram_chat_id', 'emergency_number', 'schedule_start', 'schedule_end'];
const KEY_D = ['model_file'];

const BOOL_KEYS = new Set(['item_detector', 'audio_enabled', 'manual_armed', 'schedule_enabled']);

// ---- tabs -------------------------------------------------------------------
document.querySelectorAll('.tab-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('text-emerald-400', 'text-red-400', 'border-emerald-400', 'border-red-400', 'text-slate-400'));
    const isSys = btn.dataset.tab === 'system';
    btn.classList.add(isSys ? 'text-red-400' : 'text-emerald-400', isSys ? 'border-red-400' : 'border-emerald-400');
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.add('hidden'));
    document.getElementById('tab-' + btn.dataset.tab).classList.remove('hidden');
  });
});

// ---- source type radio ---------------------------------------------------------
function setSourceType(type) {
  document.querySelectorAll('#tab-stream .opt').forEach((o) => {
    const r = o.querySelector('input');
    o.className = 'opt rounded-xl border p-3 flex items-center gap-2 cursor-pointer transition ' +
      (r.value === type ? 'border-emerald-400/50 bg-emerald-400/5' : 'border-white/10 hover:border-white/30');
  });
  document.getElementById('srcUrlWrap').classList.toggle('hidden', type !== 'rtsp');
  document.getElementById('srcFileWrap').classList.toggle('hidden', type !== 'video');
  document.getElementById('srcUploadWrap').classList.toggle('hidden', type !== 'upload');
}
document.querySelectorAll('input[name="srcType"]').forEach((r) => r.addEventListener('change', () => setSourceType(r.value)));

// ---- load ---------------------------------------------------------------------
async function loadAll() {
  const s = await (await fetch('/api/settings')).json();
  [...KEY_A, ...KEY_C, ...KEY_D].forEach((k) => { const el = document.getElementById(k); if (el) el.value = s[k] || ''; });
  KEY_B.forEach((k) => { const el = document.getElementById(k); if (el) el.checked = s[k] === '1'; });
  document.getElementById('modelChip2').textContent = s.model_file || 'default engine';

  // model file selector
  const sel = document.getElementById('model_file');
  if (sel) {
    let mods = [];
    try { mods = await (await fetch('/api/models')).json(); } catch { /* keep empty */ }
    sel.innerHTML = mods.map((m) => `<option value="${m.path}" ${m.active ? 'selected' : ''}>${m.name}</option>`).join('') || '<option value="">default</option>';
    sel.addEventListener('change', () => {
      document.getElementById('modelChip2').textContent = sel.value ? sel.value.split('\\').pop() : 'default engine';
    });
  }

  const src = await (await fetch('/api/source')).json();
  const type = src.type || 'video';
  document.querySelector(`input[name="srcType"][value="${type}"]`).checked = true;
  setSourceType(type);
  const valueInput = type === 'rtsp' ? document.getElementById('rtsp_value') : document.getElementById('file_value');
  if (valueInput) valueInput.value = src.value || '';
  document.getElementById('camera_name').value = src.camera_name || '';
  setResolved(src.resolved);
}
window.setResolved = (v) => { document.getElementById('resolveChip').textContent = 'source → ' + v; };

// ---- apply source ---------------------------------------------------------------
async function applySource() {
  const type = document.querySelector('input[name="srcType"]:checked').value;
  const valueInput = type === 'rtsp' ? document.getElementById('rtsp_value') : document.getElementById('file_value');
  let value = (valueInput?.value || '').trim();
  const camera_name = document.getElementById('camera_name').value.trim();

  if (type === 'upload') {
    const fileInput = document.getElementById('fileInput');
    if (!fileInput.files.length) { msg('srcMsg', 'pick a file to upload', true); return; }
    const fd = new FormData();
    fd.append('file', fileInput.files[0]);
    const r = await fetch('/api/upload', { method: 'POST', body: fd });
    const j = await r.json();
    if (!r.ok) { msg('srcMsg', j.detail || 'upload failed', true); return; }
    window.setResolved(j.resolved);
    msg('srcMsg', 'uploaded · stream switching');
    fillFromSource();
    return;
  }
  const r = await fetch('/api/source', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type, value, camera_name }),
  });
  if (!r.ok) { const j = await r.json(); msg('srcMsg', j.detail || 'failed', true); return; }
  window.setResolved((await r.json()).resolved);
  msg('srcMsg', 'source applied · engine reloads within seconds');
}
function fillFromSource() { setSourceType('upload'); }

function msg(id, text, isErr) {
  const el = document.getElementById(id);
  el.textContent = text;
  el.className = 'text-xs font-mono mt-1 h-4 ' + (isErr ? 'text-red-400' : 'text-emerald-400');
}
document.getElementById('btnApply')?.addEventListener('click', applySource);
document.getElementById('btnTest')?.addEventListener('click', async () => {
  const r = await (await fetch('/api/status')).json();
  document.getElementById('resolveChip').textContent = `stream → ${r.source} · ${r.fps.toFixed(1)} fps · ${r.device === '0' ? 'GPU' : 'CPU'}`;
});

// ---- save settings ------------------------------------------------------------
document.getElementById('saveAll').addEventListener('click', async () => {
  const body = {};
  [...KEY_A, ...KEY_C, ...KEY_D].forEach((k) => { body[k] = document.getElementById(k).value || ''; });
  KEY_B.forEach((k) => { body[k] = document.getElementById(k).checked ? '1' : '0'; });
  body.camera_name = document.getElementById('camera_name').value.trim();
  const r = await fetch('/api/settings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  msg('saveMsg', r.ok ? 'configuration saved ✓' : 'error saving', !r.ok);
  if (r.status === 401) window.location.href = '/login';
});

// ---- model: use default engine ----------------------------------------------------
document.getElementById('btnDefaultModel').addEventListener('click', async () => {
  document.getElementById('model_file').value = '';
  document.getElementById('modelChip2').textContent = 'default engine';
  const r = await fetch('/api/settings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model_file: '' }),
  });
  document.getElementById('tuneMsg').textContent = r.ok ? 'default engine selected · reloading' : 'error';
});

// ---- model: reset tuning to factory defaults --------------------------------------
const TUNING_DEFAULTS = { model_conf: '0.25', model_imgsz: '480', frame_skip: '2', faint_seconds: '30', msg_cooldown: '30' };
document.getElementById('btnResetTuning').addEventListener('click', async () => {
  const body = {};
  Object.entries(TUNING_DEFAULTS).forEach(([k, v]) => { body[k] = v; document.getElementById(k).value = v; });
  body.item_detector = '1';
  document.getElementById('item_detector').checked = true;
  const r = await fetch('/api/settings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  document.getElementById('tuneMsg').textContent = r.ok ? 'tuning reset to defaults ✓' : 'error';
});

// ---- system: clear database ---------------------------------------------------------
document.getElementById('btnClearDb').addEventListener('click', async () => {
  if (!window.confirm('CLEAR DATABASE? This wipes all evidence, zones and custom settings and restores factory defaults. Continue?')) return;
  const r = await fetch('/api/system/reset', { method: 'POST' });
  document.getElementById('clearMsg').textContent = r.ok ? 'database cleared · factory defaults restored' : 'error';
  setTimeout(() => window.location.reload(), 1200);
});

loadAll();