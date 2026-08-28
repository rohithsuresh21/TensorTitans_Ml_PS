/* SentinelIQ zone mapper - canvas polygon selection with notes & persistence. */

const canvas = document.getElementById('zoneCanvas');
const ctx = canvas.getContext('2d');
let points = [];
let img = null;
let existing = [];

function toast(text, kind = '') {
  const box = document.getElementById('toast');
  const el = document.createElement('div');
  el.className = 'text-xs font-mono px-3 py-1.5 rounded-lg border ' +
    (kind === 'err' ? 'border-red-500/30 bg-red-500/10 text-red-300'
      : 'border-emerald-400/30 bg-emerald-400/5 text-emerald-300');
  el.textContent = text;
  box.prepend(el);
  setTimeout(() => el.remove(), 3500);
}

async function loadSnapshot() {
  const busy = document.getElementById('pickerBusy');
  busy.classList.remove('hidden');
  let res;
  try {
    res = await fetch('/api/snapshot');
    if (res.status === 401) { window.location.href = '/login'; return; }
    if (res.status === 503) throw new Error('stream unavailable');
  } catch {
    busy.classList.add('hidden');
    toast('COULD NOT ACQUIRE FRAME — CHECK STREAM SOURCE IN SETTINGS', 'err');
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  img = new Image();
  img.onload = () => {
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    points = [];
    redraw();
    busy.classList.add('hidden');
  };
  img.src = url;
}

function redraw() {
  if (!img) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0);

  // existing saved zones (dimmed)
  existing.forEach((z) => {
    if (!Array.isArray(z.points) || z.points.length < 3) return;
    ctx.beginPath();
    z.points.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
    ctx.closePath();
    ctx.strokeStyle = 'rgba(148,163,184,0.55)';
    ctx.setLineDash([6, 4]);
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.setLineDash([]);
  });

  if (points.length < 2) return;
  ctx.beginPath();
  points.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
  if (points.length > 2) ctx.closePath();
  ctx.strokeStyle = '#34d399';
  ctx.lineWidth = 3;
  ctx.stroke();
  ctx.fillStyle = 'rgba(52,211,153,0.15)';
  ctx.fill();
  ctx.setLineDash([]);
  points.forEach((p, i) => {
    ctx.beginPath();
    ctx.arc(p[0], p[1], 6, 0, Math.PI * 2);
    ctx.fillStyle = '#ef4444';
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 1.5;
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 11px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(String(i + 1), p[0], p[1] - 9);
    ctx.textAlign = 'left';
  });
}

canvas.addEventListener('click', (e) => {
  if (!img) return;
  const rect = canvas.getBoundingClientRect();
  const x = Math.round((e.clientX - rect.left) * (canvas.width / rect.width));
  const y = Math.round((e.clientY - rect.top) * (canvas.height / rect.height));
  points.push([x, y]);
  redraw();
});

async function loadZones() {
  try {
    const list = await (await fetch('/api/zones')).json();
    existing = Array.isArray(list) ? list : [];
  } catch { existing = []; }

  const box = document.getElementById('zoneList');
  if (!existing.length) {
    box.innerHTML = '<div class="text-xs font-mono text-slate-600 col-span-full py-3">NO ZONES SAVED YET — DRAW AND SAVE ONE ABOVE</div>';
    return;
  }
  box.innerHTML = existing.map((z) => `
    <div class="rounded-xl border ${z.is_active ? 'border-emerald-400/30 bg-emerald-400/5' : 'border-white/10 bg-white/[0.03]'} p-3">
      <div class="flex items-center justify-between mb-1">
        <span class="text-xs font-semibold text-slate-200">${z.name}</span>
        ${z.is_active ? '<span class="text-[9px] font-mono text-emerald-400 border border-emerald-400/30 rounded px-1.5 py-0.5">ACTIVE</span>' : ''}
      </div>
      <div class="flex items-center justify-between mt-2">
        <span class="text-[10px] font-mono text-slate-500">${z.points.length} vertices</span>
        <button onclick="deleteZone(${z.id})" class="text-[10px] font-mono text-red-400 hover:text-red-300">DELETE</button>
      </div>
    </div>`).join('');
}

window.deleteZone = async (id) => {
  const r = await fetch('/api/zone/' + id, { method: 'DELETE' });
  if (r.ok) toast('ZONE DELETED');
  await loadZones();
  redraw();
};

document.getElementById('btnSave').addEventListener('click', async () => {
  if (points.length < 3) { toast('NEED ≥ 3 POINTS TO DEFINE ZONE', 'err'); return; }
  const name = document.getElementById('zoneName').value.trim() || 'Restricted Zone';
  const r = await fetch('/api/zone', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, points }),
  });
  if (r.status === 401) { window.location.href = '/login'; return; }
  if (!r.ok) { const j = await r.json(); toast(j.detail || 'SAVE FAILED', 'err'); return; }
  toast('ZONE SAVED · ENGINE RELOADS ACTIVE ZONES');
  points = [];
  redraw();
  await loadZones();
});

document.getElementById('btnClear').addEventListener('click', () => {
  points = [];
  redraw();
  toast('POINTS CLEARED — START A FRESH BOUNDARY');
});

document.getElementById('btnNew').addEventListener('click', () => {
  points = [];
  document.getElementById('zoneName').value = 'Restricted Zone ' + (existing.length + 1);
  redraw();
  toast('NEW ZONE READY — CLICK CORNERS');
});

document.getElementById('btnReload').addEventListener('click', loadSnapshot);

loadSnapshot();
loadZones();