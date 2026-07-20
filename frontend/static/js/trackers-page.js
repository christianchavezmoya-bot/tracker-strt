/**
 * HOLO-RTLS — Trackers page: discovery scan, acknowledge, purge, extended table.
 */
'use strict';

if (!API.isLoggedIn()) location.href = '/login';

let scanTimer = null;
let scanIntervalSec = 60;
let positions = [];
let orgSections = [];
let scanCatalog = [];
let selectedIds = new Set();
let ackTracker = null;
let ackIsEdit = false;
let currentView = 'table';
let cachedTrackers = [];

function fmtLastSeen(t) {
  const iso = t.last_seen_at;
  const ts = t.last_report_time;
  if (iso) {
    try {
      const d = new Date(iso);
      if (!Number.isNaN(d.getTime())) {
        return d.toLocaleString(undefined, {
          month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
        });
      }
    } catch (_) { /* ignore */ }
  }
  if (ts) {
    try {
      return new Date(ts * 1000).toLocaleString(undefined, {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
      });
    } catch (_) { /* ignore */ }
  }
  return '—';
}

const ACK = { UNACKNOWLEDGED: 'Unacknowledged', ACTIVE: 'Active', INACTIVE: 'Inactive', UNKNOWN: 'Unknown' };
const FEAT_LABELS = {
  positioning: 'Position',
  proximity: 'Proximity',
  restricted_zone: 'No-go zone',
  low_battery: 'Low battery',
  no_signal: 'Offline alert',
  lone_worker: 'Lone worker',
  sos: 'SOS',
  temperature: 'Temperature',
};

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function fmtCoords(t) {
  if (!t.position) return '—';
  const x = Number(t.position.x || 0).toFixed(1);
  const y = Number(t.position.y || 0).toFixed(1);
  return `${x}, ${y}`;
}

function fmtBeacons(t) {
  const b = t.beacon_detections || [];
  if (!b.length) return '—';
  return b.map(x => `${x.node}:${Math.round(x.rssi)}`).join(', ');
}

function displayStatus(t) {
  if (t.ack_status === 'UNACKNOWLEDGED' || t.ack_status_id === 0) return 'Unacknowledged';
  if (t.asset_state === 'OFFLINE' || t.asset_state_id === 2) return 'Offline';
  if (t.ack_status === 'INACTIVE') return 'Inactive';
  if (t.ack_status === 'ACTIVE') return 'Active';
  return t.ack_status || 'Unknown';
}

function featCells(t) {
  const feats = t.features || {};
  const keys = ['proximity', 'lone_worker', 'restricted_zone', 'low_battery', 'sos'];
  return keys.map(k => {
    if (feats[k] === undefined) return '<td class="muted">—</td>';
    return `<td>${feats[k] ? '<i class="fa-solid fa-check" style="color:var(--green)"></i>' : '—'}</td>`;
  }).join('');
}

async function loadMeta() {
  const [posRes, secRes, catRes, cfgRes] = await Promise.all([
    API.get('/settings/org/positions'),
    API.get('/settings/org/sections'),
    API.get('/trackers/scan/types'),
    API.get('/trackers/scan/config'),
  ]);
  positions = (await API.json(posRes))?.items || [];
  orgSections = (await API.json(secRes))?.items || [];
  scanCatalog = (await API.json(catRes))?.scan_types || [];
  const cfg = await API.json(cfgRes);
  if (cfg) {
    scanIntervalSec = cfg.interval_sec || 60;
    document.getElementById('scanIntervalSelect').value = String(scanIntervalSec);
    renderScanTypeChecks(cfg.scan_types || []);
  }
}

function renderScanTypeChecks(selected) {
  const el = document.getElementById('scanTypeChecks');
  if (!el) return;
  el.innerHTML = scanCatalog.map(st => `
    <label class="scan-type-item">
      <input type="checkbox" value="${esc(st.id)}" ${selected.includes(st.id) ? 'checked' : ''}>
      <span>${esc(st.label)}</span>
    </label>`).join('');
}

async function loadTrackers() {
  const q = document.getElementById('qInput').value.trim();
  const ack = document.getElementById('filterAck').value;
  const params = new URLSearchParams({ per_page: 200, include_decommissioned: 'true' });
  if (q) params.set('q', q);
  if (ack) params.set('ack_status', ack);

  const res = await API.get('/trackers?' + params);
  const data = await API.json(res);
  const items = data.items || [];
  cachedTrackers = items;

  document.getElementById('statTotal').textContent = data.total ?? items.length;
  document.getElementById('statUnack').textContent = items.filter(t =>
    t.ack_status === 'UNACKNOWLEDGED' || t.ack_status_id === 0).length;
  document.getElementById('statActive').textContent = items.filter(t =>
    t.ack_status === 'ACTIVE' && t.asset_state !== 'OFFLINE').length;
  document.getElementById('statOffline').textContent = items.filter(t =>
    t.asset_state === 'OFFLINE').length;

  const body = document.getElementById('trackersBody');
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="19" class="empty-cell">No tags yet. Run a scan or adjust filters.</td></tr>';
    return;
  }

  body.innerHTML = items.map(t => {
    const checked = selectedIds.has(t.id) ? 'checked' : '';
    const bat = t.battery_level != null ? Math.round(t.battery_level) + '%' : '—';
    const rssi = t.last_rssi != null ? Math.round(t.last_rssi) + ' dBm' : '—';
    const name = [t.first_name, t.surname].filter(Boolean).join(' ') || '—';
    const lastTx = fmtLastSeen(t);
    return `<tr data-id="${t.id}">
      <td><input type="checkbox" class="row-check" data-id="${t.id}" ${checked}></td>
      <td class="mono">${esc(t.hardware_id)}</td>
      <td>${esc(t.device_model || '—')}</td>
      <td><span class="chip">${esc(displayStatus(t))}</span></td>
      <td class="mono" title="${esc(t.last_seen_at || '')}">${esc(lastTx)}</td>
      <td>${bat}</td>
      <td>${esc(t.nickname || '—')}</td>
      <td>${esc(name)}</td>
      <td>${rssi}</td>
      ${featCells(t)}
      <td class="mono">${fmtCoords(t)}</td>
      <td>${esc(t.nearest_node || '—')}</td>
      <td class="mono beacon-col" title="${esc(fmtBeacons(t))}">${esc(fmtBeacons(t))}</td>
      <td class="row-actions">
        <button class="icon-btn" title="Acknowledge" data-role-min="operator" onclick="openAck(${t.id})"><i class="fa-solid fa-circle-check"></i></button>
        <button class="icon-btn" title="Edit" data-role-min="operator" onclick="openEdit(${t.id})"><i class="fa-solid fa-pen"></i></button>
        <a class="icon-btn" title="Map" href="/?tracker=${t.id}"><i class="fa-solid fa-location-crosshairs"></i></a>
      </td>
    </tr>`;
  }).join('');

  body.querySelectorAll('.row-check').forEach(cb => {
    cb.onchange = () => {
      const id = parseInt(cb.dataset.id, 10);
      if (cb.checked) selectedIds.add(id); else selectedIds.delete(id);
      syncSelectAll();
    };
  });
}

function syncSelectAll() {
  const all = document.querySelectorAll('.row-check');
  const chk = document.getElementById('selectAll');
  if (!chk || !all.length) return;
  chk.checked = all.length > 0 && [...all].every(c => c.checked);
}

function getSelectedIds() {
  return [...selectedIds];
}

async function runScan() {
  const btn = document.getElementById('btnRefresh');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i>';
  try {
    const res = await API.post('/trackers/scan/run', {});
    const data = await API.json(res);
    if (res.ok) {
      showToast(`Scan: ${data.created} new, ${data.updated} updated`, 'success');
      await loadTrackers();
      if (currentView === 'chart') await loadTimelineChart();
    } else {
      showToast(data.error || 'Scan failed', 'error');
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-rotate"></i> Refresh';
  }
}

function scheduleScan() {
  clearInterval(scanTimer);
  scanTimer = setInterval(runScan, scanIntervalSec * 1000);
}

async function saveScanSettings() {
  const types = [...document.querySelectorAll('#scanTypeChecks input:checked')].map(c => c.value);
  const interval = parseInt(document.getElementById('scanIntervalSelect').value, 10);
  const res = await API.patch('/trackers/scan/config', { scan_types: types, interval_sec: interval });
  const data = await API.json(res);
  if (res.ok) {
    scanIntervalSec = data.interval_sec;
    scheduleScan();
    closeScanModal();
    showToast('Scan settings saved', 'success');
  }
}

function openScanModal() {
  document.getElementById('scanModal').hidden = false;
}

function closeScanModal() {
  document.getElementById('scanModal').hidden = true;
}

async function openAck(id) {
  const res = await API.get('/trackers/' + id);
  const data = await API.json(res);
  if (!res.ok) return;
  ackTracker = data.tracker;
  ackIsEdit = false;
  fillAckForm(ackTracker, false);
  document.getElementById('ackModal').hidden = false;
}

async function openEdit(id) {
  const res = await API.get('/trackers/' + id);
  const data = await API.json(res);
  if (!res.ok) return;
  ackTracker = data.tracker;
  ackIsEdit = true;
  fillAckForm(ackTracker, true);
  document.getElementById('ackModal').hidden = false;
}

async function fillAckForm(t, isEdit) {
  const st = t.scan_type || 'UNKNOWN_BLE';
  const catRes = await API.get('/trackers/scan/types');
  const cat = await API.json(catRes);
  const typeInfo = (cat.scan_types || []).find(x => x.id === st) || { features: [] };

  document.getElementById('ackTitle').textContent =
    `${isEdit ? 'Edit' : 'Acknowledge'} — ${t.hardware_id} · ${t.device_model || st}`;

  document.getElementById('ackNickname').value = t.nickname || '';
  document.getElementById('ackFirstName').value = t.first_name || '';
  document.getElementById('ackSurname').value = t.surname || '';
  document.getElementById('ackUsername').value = t.username || '';
  document.getElementById('ackDob').value = t.date_of_birth || '';
  document.getElementById('ackPhone').value = t.phone || '';

  const posSel = document.getElementById('ackPosition');
  posSel.innerHTML = '<option value="">— Select —</option>' +
    positions.map(p => `<option value="${p.id}" ${t.position_id === p.id ? 'selected' : ''}>${esc(p.name)}</option>`).join('');

  const secSel = document.getElementById('ackSection');
  secSel.innerHTML = '<option value="">— Select —</option>' +
    orgSections.map(s => `<option value="${s.id}" ${t.org_section_id === s.id ? 'selected' : ''}>${esc(s.name)}</option>`).join('');

  const featEl = document.getElementById('ackFeatures');
  const enabled = t.features || {};
  featEl.innerHTML = (typeInfo.features || []).map(f => `
    <label class="feat-check">
      <input type="checkbox" data-feat="${esc(f.key)}" ${enabled[f.key] !== false ? 'checked' : ''}>
      <span>${esc(f.label)}</span>
    </label>`).join('') || '<p class="muted">No configurable features for this tag type.</p>';
}

async function saveAck() {
  if (!ackTracker) return;
  const features = {};
  document.querySelectorAll('#ackFeatures [data-feat]').forEach(cb => {
    features[cb.dataset.feat] = cb.checked;
  });
  const body = {
    nickname: document.getElementById('ackNickname').value.trim(),
    first_name: document.getElementById('ackFirstName').value.trim(),
    surname: document.getElementById('ackSurname').value.trim(),
    username: document.getElementById('ackUsername').value.trim(),
    date_of_birth: document.getElementById('ackDob').value.trim(),
    phone: document.getElementById('ackPhone').value.trim(),
    position_id: parseInt(document.getElementById('ackPosition').value, 10) || null,
    org_section_id: parseInt(document.getElementById('ackSection').value, 10) || null,
    features,
  };
  let res;
  if (ackIsEdit && ackTracker.ack_status === 'ACTIVE') {
    res = await API.patch('/trackers/' + ackTracker.id, body);
  } else {
    res = await API.post('/trackers/' + ackTracker.id + '/acknowledge', body);
  }
  if (res.ok) {
    closeAckModal();
    loadTrackers();
    showToast('Tag saved', 'success');
  } else {
    const err = await API.json(res);
    showToast(err.error || 'Save failed', 'error');
  }
}

function closeAckModal() {
  document.getElementById('ackModal').hidden = true;
  ackTracker = null;
}

async function purgeSelected() {
  const ids = getSelectedIds();
  if (!ids.length) { showToast('Select one or more tags', 'warning'); return; }
  if (!(await holoConfirm('Purge selected tags? All profile data will be cleared and tags become unacknowledged.', { danger: true }))) return;
  const res = await API.post('/trackers/bulk/purge', { ids });
  if (res.ok) {
    selectedIds.clear();
    loadTrackers();
    showToast('Tags purged', 'success');
  }
}

async function ackSelected() {
  const ids = getSelectedIds();
  if (ids.length !== 1) {
    showToast('Select exactly one unacknowledged tag to acknowledge', 'warning');
    return;
  }
  openAck(ids[0]);
}

window.openAck = openAck;
window.openEdit = openEdit;

function setView(mode) {
  currentView = mode;
  const tablePanel = document.getElementById('tablePanel');
  const chartPanel = document.getElementById('chartPanel');
  const tableBtn = document.getElementById('viewTableBtn');
  const chartBtn = document.getElementById('viewChartBtn');
  if (mode === 'chart') {
    tablePanel.classList.add('hidden');
    chartPanel.classList.add('active');
    tableBtn.classList.remove('active');
    chartBtn.classList.add('active');
    loadTimelineChart();
  } else {
    tablePanel.classList.remove('hidden');
    chartPanel.classList.remove('active');
    tableBtn.classList.add('active');
    chartBtn.classList.remove('active');
  }
}

function rssiToY(rssi, rowTop, rowH) {
  const clamped = Math.max(-100, Math.min(-40, rssi));
  const norm = (clamped + 100) / 60;
  return rowTop + rowH - norm * rowH * 0.85 - rowH * 0.05;
}

function drawTimelineChart(data) {
  const canvas = document.getElementById('timelineCanvas');
  if (!canvas) return;
  const trackers = data.trackers || [];
  const rowH = 72;
  const padL = 200;
  const padR = 48;
  const padT = 28;
  const padB = 36;
  const width = Math.max(720, canvas.parentElement.clientWidth - 24);
  const height = Math.max(200, padT + padB + trackers.length * rowH);
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#0a0e14';
  ctx.fillRect(0, 0, width, height);

  const now = Date.now();
  const windowMs = (data.window_minutes || 60) * 60 * 1000;
  const t0 = now - windowMs;
  const plotW = width - padL - padR;

  function xAt(ts) {
    const t = new Date(ts).getTime();
    return padL + ((t - t0) / windowMs) * plotW;
  }

  ctx.strokeStyle = 'rgba(148,163,184,.25)';
  ctx.fillStyle = 'rgba(148,163,184,.55)';
  ctx.font = '11px system-ui,sans-serif';
  const tickCount = Math.min(8, Math.max(4, Math.floor(data.window_minutes / 15) || 4));
  for (let i = 0; i <= tickCount; i++) {
    const frac = i / tickCount;
    const x = padL + frac * plotW;
    ctx.beginPath();
    ctx.moveTo(x, padT);
    ctx.lineTo(x, height - padB);
    ctx.stroke();
    const tickTime = new Date(t0 + frac * windowMs);
    ctx.fillText(tickTime.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }), x - 20, height - 12);
  }

  ctx.fillStyle = 'rgba(148,163,184,.8)';
  ctx.fillText(`${data.window_minutes} min window`, width - padR - 70, 18);

  if (!trackers.length) {
    ctx.fillStyle = '#64748b';
    ctx.fillText('No acknowledged tags with timeline data. Acknowledge tags and run scans.', padL, padT + 40);
    return;
  }

  trackers.forEach((tr, idx) => {
    const rowTop = padT + idx * rowH;
    const midY = rowTop + rowH / 2;

    ctx.fillStyle = 'rgba(107,255,71,.08)';
    ctx.fillRect(padL, rowTop + 4, plotW, rowH - 8);

    ctx.fillStyle = '#e2e8f0';
    ctx.font = '12px system-ui,sans-serif';
    const label = tr.label.length > 28 ? tr.label.slice(0, 26) + '…' : tr.label;
    ctx.fillText(label, 8, midY - 4);
    ctx.fillStyle = '#64748b';
    ctx.font = '10px monospace';
    ctx.fillText(tr.hardware_id, 8, midY + 12);

    const samples = tr.samples || [];
    samples.forEach(s => {
      const x = xAt(s.timestamp);
      if (s.online === false) {
        ctx.strokeStyle = '#ff4444';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x, rowTop + 6);
        ctx.lineTo(x, rowTop + rowH - 6);
        ctx.stroke();
      }
    });

    ctx.strokeStyle = '#cbd5e1';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    let started = false;
    samples.forEach(s => {
      if (!s.online || s.rssi == null) return;
      const x = xAt(s.timestamp);
      const y = rssiToY(s.rssi, rowTop, rowH);
      if (!started) { ctx.moveTo(x, y); started = true; }
      else ctx.lineTo(x, y);
    });
    if (started) ctx.stroke();

    ctx.strokeStyle = 'rgba(148,163,184,.15)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, rowTop + rowH);
    ctx.lineTo(width - padR, rowTop + rowH);
    ctx.stroke();
  });
}

async function loadTimelineChart() {
  const minutes = parseInt(document.getElementById('chartWindow').value, 10) || 60;
  const ids = getSelectedIds();
  let url = `/trackers/presence/timeline?minutes=${minutes}`;
  if (ids.length) url += '&tracker_ids=' + ids.join(',');
  const res = await API.get(url);
  const data = await API.json(res);
  if (res.ok) drawTimelineChart(data);
}

document.getElementById('viewTableBtn').onclick = () => setView('table');
document.getElementById('viewChartBtn').onclick = () => setView('chart');
document.getElementById('chartWindow').onchange = loadTimelineChart;
document.getElementById('btnChartRefresh').onclick = loadTimelineChart;

document.getElementById('btnScanSettings').onclick = openScanModal;
document.getElementById('btnRefresh').onclick = runScan;
document.getElementById('btnPurge').onclick = purgeSelected;
document.getElementById('btnAcknowledge').onclick = ackSelected;
document.getElementById('scanModalClose').onclick = closeScanModal;
document.getElementById('scanCancel').onclick = closeScanModal;
document.getElementById('scanSave').onclick = saveScanSettings;
document.getElementById('ackCancel').onclick = closeAckModal;
document.getElementById('ackSave').onclick = saveAck;
document.getElementById('selectAll').onchange = e => {
  document.querySelectorAll('.row-check').forEach(cb => {
    cb.checked = e.target.checked;
    const id = parseInt(cb.dataset.id, 10);
    if (e.target.checked) selectedIds.add(id); else selectedIds.delete(id);
  });
};

['qInput', 'filterAck'].forEach(id => {
  document.getElementById(id).addEventListener('change', loadTrackers);
  document.getElementById(id).addEventListener('keyup', e => { if (e.key === 'Enter') loadTrackers(); });
});

if (window.HoloRBAC) HoloRBAC.hideViewerActions();

(async () => {
  await loadMeta();
  await loadTrackers();
  scheduleScan();
})();
