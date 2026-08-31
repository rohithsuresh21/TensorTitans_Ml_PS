/* SentinelIQ command dashboard - telemetry, charts, evidence feed. */

function postJSON(url, body = {}) {
  return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
}

function fmtTime(ts, withDate = false) {
  const d = new Date(ts * 1000);
  return withDate ? d.toLocaleDateString('en-GB') + ' ' + d.toLocaleTimeString('en-GB') : d.toLocaleTimeString('en-GB');
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// ---- clock -------------------------------------------------------------------
function tickClock() {
  const el = document.getElementById('clockLine');
  if (el) el.textContent = `${new Date().toLocaleTimeString('en-GB')} · SYNCHRONIZED`;
}
setInterval(tickClock, 1000); tickClock();

// ---- viewer heartbeat (keeps local beep alive while this tab is open) ----------
setInterval(() => postJSON('/api/viewer/heartbeat').catch(() => {}), 3000);
postJSON('/api/viewer/heartbeat').catch(() => {});

// ---- animated counters -----------------------------------------------------
function animate(elId, target) {
  const el = document.getElementById(elId);
  if (!el) return;
  const from = parseFloat(el.dataset.v || 0);
  if (from === target) { el.textContent = String(target); return; }
  el.dataset.v = target;
  const start = performance.now();
  function step(t) {
    const k = Math.min(1, (t - start) / 500);
    el.textContent = String(Math.round(from + (target - from) * (1 - Math.pow(1 - k, 3))));
    if (k < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

// ---- charts -------------------------------------------------------------------
Chart.defaults.color = '#64748b';
Chart.defaults.font.family = "'Manrope','sans-serif'";
Chart.defaults.font.size = 11;

const actEl = document.getElementById('activityChart');
const mixEl = document.getElementById('mixChart');

const activityChart = actEl ? new Chart(actEl, {
  type: 'line',
  data: {
    labels: [],
    datasets: [{
      label: 'Threat Index',
      data: [],
      borderColor: '#10b981',
      borderWidth: 2.5,
      backgroundColor: (ctx) => {
        const { chart } = ctx;
        const { ctx: c, chartArea } = chart;
        if (!chartArea) return 'rgba(16,185,129,0.12)';
        const g = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
        g.addColorStop(0, 'rgba(16,185,129,0.45)');
        g.addColorStop(1, 'rgba(16,185,129,0.02)');
        return g;
      },
      tension: 0.4, fill: true, pointRadius: 0, pointHitRadius: 12,
    }],
  },
  options: {
    responsive: true, maintainAspectRatio: false, animation: { duration: 250 },
    interaction: { mode: 'index', intersect: false },
    scales: {
      y: { beginAtZero: true, suggestedMax: 100, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { maxTicksLimit: 4 } },
      x: { grid: { display: false }, ticks: { maxTicksLimit: 6, maxRotation: 0 } },
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: 'rgba(5,7,13,0.9)', borderColor: 'rgba(16,185,129,0.3)', borderWidth: 1,
        titleFont: { family: "'JetBrains Mono','monospace'", size: 10 },
        bodyFont: { family: "'JetBrains Mono','monospace'", size: 11 },
        callbacks: { label: (c) => ` THREAT ${c.parsed.y}%` },
      },
    },
  },
}) : null;

const mixChart = mixEl ? new Chart(mixEl, {
  type: 'doughnut',
  data: {
    labels: ['ZONE BREACH', 'MEDICAL'],
    datasets: [{ data: [0, 0], backgroundColor: ['#10b981', '#ef4444'], hoverOffset: 6, borderWidth: 2, borderColor: '#05070d' }],
  },
  options: {
    responsive: true, maintainAspectRatio: false, cutout: '68%',
    plugins: {
      legend: { position: 'bottom', labels: { boxWidth: 8, boxHeight: 8, usePointStyle: true, font: { size: 10 }, color: '#94a3b8' } },
      tooltip: { backgroundColor: 'rgba(5,7,13,0.9)', borderColor: 'rgba(148,163,184,0.2)', borderWidth: 1 },
    },
  },
}) : null;

const SCAN = 30;
let scanData = Array.from({ length: SCAN }, () => 0);
let timeData = Array.from({ length: SCAN }, () => '');

// ---- status polling ------------------------------------------------------------
async function refresh() {
  let s;
  try {
    const r = await fetch('/api/status');
    if (r.status === 401) { window.location.href = '/login'; return; }
    s = await r.json();
  } catch { return; }

  const st = document.getElementById('bigStatus');
  st.className = s.armed
    ? 'flex items-center gap-2 px-3 py-1.5 rounded-lg border font-mono text-xs tracking-widest border-emerald-400/40 text-emerald-300 bg-emerald-400/10'
    : 'flex items-center gap-2 px-3 py-1.5 rounded-lg border font-mono text-xs tracking-widest border-slate-600/40 text-slate-400 bg-white/5';
  st.querySelector('span.dot').className = 'dot w-2 h-2 rounded-full ' + (s.armed ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500');
  st.querySelector('span:last-child').textContent = s.armed ? 'ARMED' : 'DISARMED';

  setText('fpsChip', `FPS ${(s.fps || 0).toFixed(0)}`);
  setText('modelChip', `${s.model.split('-')[0] || 'MODEL'} · ${s.device === '0' ? 'GPU' : 'CPU'}`);
  setText('camLabel', `${s.camera} · ${s.zones} zone(s)`);
  setText('scheduleNote', s.schedule.enabled ? `SCHEDULE: ${s.schedule.start}–${s.schedule.end} AUTO-ARM` : 'SCHEDULE: MANUAL');

  const armToggle = document.getElementById('armToggle');
  if (armToggle && armToggle.checked !== (s.settings.manual_armed === '1')) armToggle.checked = s.settings.manual_armed === '1';

  const e = s.events[0] || {};
  const intruder = e.intruders || 0, faint = e.faints || 0, hand = e.hands_up || 0;
  const threat = Math.min(100, Math.round(intruder * 35 + faint * 45 + hand * 15 + (s.armed ? 5 : 0)));

  // threat gauge (dashoffset 0-100)
  const arc = document.getElementById('gaugeArc');
  if (arc) {
    arc.style.strokeDashoffset = String(100 - threat);
    arc.setAttribute('stroke', threat > 70 ? '#ef4444' : threat > 35 ? '#f59e0b' : '#10b981');
  }
  setText('threatPct', String(threat));

  const vio = document.getElementById('violations');
  const rows = [];
  if (intruder) rows.push(['<span class="text-emerald-400">●</span> ZONE BREACH', `${intruder} subject(s)`]);
  if (faint) rows.push(['<span class="text-red-400">●</span> MEDICAL', `${faint} faint`]);
  if (hand) rows.push(['<span class="text-yellow-400">●</span> HANDS-UP', `${hand} pose`]);
  vio.innerHTML = rows.length
    ? rows.map(([a, b]) => `<div class="flex justify-between items-center rounded-lg bg-white/5 border border-white/10 px-3 py-1.5"><span>${a}</span><span class="font-mono">${b}</span></div>`).join('')
    : '<div class="text-slate-600 text-center py-2">ALL CLEAR</div>';

  const alertChip = document.getElementById('alertChip');
  const active = intruder || faint;
  setText('alertChip', active ? '⚠ ACTIVE ALERT' : 'STANDBY');
  alertChip.className = 'px-2 py-0.5 text-[10px] font-mono bg-black/60 backdrop-blur rounded border ' +
    (active ? 'border-red-500/50 text-red-300 animate-pulse' : 'border-white/10 text-slate-400');

  setText('recChip', s.armed ? 'REC' : 'IDLE');
  const img = document.getElementById('liveStream');
  if (img && img.naturalWidth) setText('resChip', `${img.naturalWidth}×${img.naturalHeight}`);

  document.getElementById('barIntruders').style.width = Math.min(100, intruder * 40) + '%';
  document.getElementById('barHands').style.width = Math.min(100, hand * 40) + '%';
  document.getElementById('barFaints').style.width = Math.min(100, faint * 40) + '%';

  // activity chart
  scanData.push(threat); scanData.shift();
  timeData.push(new Date().toLocaleTimeString('en-GB')); timeData.shift();
  if (activityChart) {
    activityChart.data.labels = timeData;
    activityChart.data.datasets[0].data = scanData;
    activityChart.update('none');
  }
  if (mixChart) {
    mixChart.data.datasets[0].data = [
      s.events.filter((ev) => ev.type === 'ZONE BREACH').length,
      s.events.filter((ev) => ev.type === 'MEDICAL EMERGENCY').length,
    ];
    mixChart.update('none');
  }

  animate('kpiIntruders', intruder);
  animate('kpiHands', hand);
  animate('kpiFaints', faint);
  animate('kpiAlerts', s.events.length);
}

// ---- evidence: latest intrusion + carried items + feed + grid -------------------
const WEAPONS = new Set(['knife', 'scissors', 'baseball bat']);

function itemChip(it, weapon) {
  const isW = WEAPONS.has(it);
  return `<span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/5 border border-white/10 ${isW || weapon ? 'text-red-300 border-red-500/30 bg-red-500/10' : 'text-slate-200'}">${it}</span>`;
}

async function refreshEvidence() {
  let list;
  try {
    const r = await fetch('/api/evidence?limit=12');
    if (r.status !== 200) return;
    list = await r.json();
  } catch { return; }
  lastEvidence = list;

  const weaponFound = list.find((x) => x.has_weapon);
  const wb = document.getElementById('weaponBadge');
  const wl = document.getElementById('weaponLine');
  if (weaponFound) {
    wb.classList.remove('hidden');
    wl.textContent = `${weaponFound.items.join(' · ')} @ ${fmtTime(weaponFound.created)}`;
  } else { wb.classList.add('hidden'); wl.textContent = ''; }

  // latest intrusion card
  const wrap = document.getElementById('lastEvWrap');
  if (list.length && wrap) {
    const ev = list[0];
    wrap.innerHTML = `<img src="/api/evidence/${ev.id}/image" class="absolute inset-0 w-full h-full object-cover cursor-pointer" onclick="openEvidence(${ev.id})" />`;
    setText('lastEvTime', fmtTime(ev.created, true));
    document.getElementById('lastEvItems').innerHTML = (ev.items.length
      ? ev.items.map((i) => itemChip(i, ev.has_weapon)).join('')
      : '<span class="text-[10px] font-mono text-slate-600">no items detected</span>')
      + (ev.has_weapon ? '<span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-red-500/20 text-red-300 border border-red-500/30">⚠ WEAPON</span>' : '');
    document.getElementById('lastEvMeta').innerHTML = `${ev.zone || 'zone'} · ${ev.camera || 'camera'} · ${ev.count} subject(s) · ${ev.event_type}`;
  } else if (wrap) {
    wrap.innerHTML = '<div class="absolute inset-0 flex items-center justify-center text-xs font-mono text-slate-600">WAITING FOR FIRST EVENT</div>';
    document.getElementById('lastEvItems').innerHTML = '';
    document.getElementById('lastEvMeta').innerHTML = '';
  }

  // carried-items panel
  const cw = document.getElementById('carriedWrap');
  if (cw) {
    if (!list.length) {
      cw.innerHTML = '<div class="text-xs font-mono text-slate-600 py-6 text-center">SCANNING INTRUDER CROPS FOR CARRIED ITEMS</div>';
      setText('carriedVer', '--');
      setText('carriedRisk', 'UNAVAILABLE');
    } else {
      const agg = {};
      list.forEach((ev) => ev.items.forEach((it) => { agg[it] = (agg[it] || 0) + 1; }));
      const entries = Object.entries(agg).sort((a, b) => b[1] - a[1]);
      cw.innerHTML = entries.length
        ? `<div class="space-y-2 mb-4">${entries.map(([name, n]) => `
            <div class="flex items-center justify-between rounded-lg bg-white/[0.03] border border-white/10 px-3 py-2">
              <span class="text-xs font-mono ${WEAPONS.has(name) ? 'text-red-300' : 'text-slate-300'}">${WEAPONS.has(name) ? '🗡' : '▦'} ${name}</span>
              <span class="text-[10px] font-mono text-slate-500">${n}×</span>
            </div>`).join('')}</div>`
        : '<div class="text-xs font-mono text-slate-600 py-4 text-center">No carried items detected across captures</div>';
      const armed = list.some((ev) => ev.has_weapon);
      const risk = document.getElementById('carriedRisk');
      risk.textContent = armed ? '⚠ ARMED SUBJECT' : (entries.length ? '✓ SUBJECT UNARMED' : '— NO THREAT ITEMS');
      risk.className = 'font-display font-bold tracking-widest text-sm mt-1.5 ' +
        (armed ? 'text-red-400' : entries.length ? 'text-emerald-400' : 'text-slate-400');
      setText('carriedVer', `${list.length} CAPTURES ANALYZED`);
    }
  }

  // recent alerts feed
  const feed = document.getElementById('alertFeed');
  if (list.length) {
    feed.innerHTML = list.map((ev) => `
      <div class="flex items-center gap-3 rounded-xl bg-white/[0.03] border border-white/10 px-3 py-2 cursor-pointer hover:bg-white/[0.06] transition" onclick="openEvidence(${ev.id})">
        <img src="/api/evidence/${ev.id}/image" loading="lazy" class="w-14 h-10 rounded object-cover shrink-0" />
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="text-[10px] font-mono ${ev.event_type.includes('MEDICAL') ? 'text-red-400' : 'text-emerald-400'}">${ev.event_type}</span>
            <span class="text-[9px] font-mono text-slate-500">${fmtTime(ev.created)}</span>
            ${ev.has_weapon ? '<span class="text-[9px] font-mono px-1 rounded bg-red-500/20 text-red-300">⚠ WEAPON</span>' : ''}
          </div>
          <div class="text-[10px] font-mono text-slate-500 truncate">${ev.zone} · ${ev.camera} · carried: ${ev.items.length ? ev.items.join(', ') : 'none'}</div>
        </div>
      </div>`).join('');
  } else {
    feed.innerHTML = '<div class="text-xs font-mono text-slate-600 py-6 text-center">NO ALERT EVENTS YET</div>';
  }

  // evidence grid
  const grid = document.getElementById('evidenceGrid');
  if (!list.length) {
    grid.innerHTML = '<div class="col-span-full text-center text-xs font-mono text-slate-600 py-6">NO EVIDENCE CAPTURES YET — INTRUSIONS WILL BE LOGGED HERE WITH CARRIED-ITEM ANALYSIS</div>';
    return;
  }
  grid.innerHTML = list.map((ev) => `
    <div class="rounded-xl overflow-hidden bg-white/[0.04] border border-white/10 group relative cursor-pointer hover:border-emerald-400/30 transition" onclick="openEvidence(${ev.id})">
      <img src="/api/evidence/${ev.id}/image" loading="lazy" class="w-full h-28 object-cover group-hover:scale-105 transition duration-500" />
      <div class="p-2.5 space-y-1.5">
        <div class="flex items-center justify-between">
          <span class="text-[10px] font-mono ${ev.event_type.includes('MEDICAL') ? 'text-red-400' : 'text-emerald-400'}">${ev.event_type}</span>
          <span class="text-[9px] font-mono text-slate-500">${fmtTime(ev.created)}</span>
        </div>
        <div class="flex flex-wrap gap-1">${ev.items.map((i) => itemChip(i, ev.has_weapon)).join('') || '<span class="text-[9px] font-mono text-slate-600">no items</span>'}</div>
        <div class="text-[9px] font-mono text-slate-600 truncate">${ev.zone || 'zone'} · ${ev.count} subject(s)</div>
      </div>
    </div>`).join('');
}

document.getElementById('armToggle')?.addEventListener('change', (e) => postJSON('/api/arm', { armed: e.target.checked }).catch(() => {}));
refresh(); refreshEvidence();
setInterval(refresh, 2000);
setInterval(refreshEvidence, 5000);

// ---- fullscreen evidence viewer ---------------------------------------------------
let lastEvidence = [];

function openEvidence(id) {
  if (!lastEvidence.length) return;
  const ev = lastEvidence.find((x) => x.id === id);
  document.getElementById('lbImg').src = `/api/evidence/${id}/image`;
  const meta = document.getElementById('lbMeta');
  if (ev) {
    meta.innerHTML = [
      `<span class="px-2 py-1 rounded border ${ev.event_type.includes('MEDICAL') ? 'border-red-500/30 text-red-300 bg-red-500/10' : 'border-emerald-400/30 text-emerald-300 bg-emerald-400/10'}">${ev.event_type}</span>`,
      ev.has_weapon ? '<span class="px-2 py-1 rounded border border-red-500/40 text-red-300 bg-red-500/10">⚠ WEAPON</span>' : '',
      `<span class="text-slate-400">${fmtTime(ev.created, true)}</span>`,
      `<span class="text-slate-400">zone · ${ev.zone}</span>`,
      `<span class="text-slate-400">cam · ${ev.camera}</span>`,
      `<span class="text-slate-400">subjects · ${ev.count}</span>`,
      ...ev.items.map((i) => itemChip(i, ev.has_weapon)),
    ].filter(Boolean).join('');
  } else {
    meta.innerHTML = '';
  }
  const lb = document.getElementById('lightbox');
  lb.classList.remove('hidden');
  lb.classList.add('flex');
}

function closeLightbox() {
  const lb = document.getElementById('lightbox');
  lb.classList.add('hidden');
  lb.classList.remove('flex');
}
document.getElementById('lbClose')?.addEventListener('click', closeLightbox);
document.getElementById('lightbox')?.addEventListener('click', (e) => { if (e.target.id === 'lightbox') closeLightbox(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeLightbox(); });