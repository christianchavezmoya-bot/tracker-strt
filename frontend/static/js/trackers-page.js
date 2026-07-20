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

  document.getElementById('statTotal').textContent = data.total ?? items.length;
  document.getElementById('statUnack').textContent = items.filter(t =>
    t.ack_status === 'UNACKNOWLEDGED' || t.ack_status_id === 0).length;
  document.getElementById('statActive').textContent = items.filter(t =>
    t.ack_status === 'ACTIVE' && t.asset_state !== 'OFFLINE').length;
  document.getElementById('statOffline').textContent = items.filter(t =>
    t.asset_state === 'OFFLINE').length;

  const body = document.getElementById('trackersBody');
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="18" class="empty-cell">No tags yet. Run a scan or adjust filters.</td></tr>';
    return;
  }

  body.innerHTML = items.map(t => {
    const checked = selectedIds.has(t.id) ? 'checked' : '';
    const bat = t.battery_level != null ? Math.round(t.battery_level) + '%' : '—';
    const rssi = t.last_rssi != null ? Math.round(t.last_rssi) + ' dBm' : '—';
    const name = [t.first_name, t.surname].filter(Boolean).join(' ') || '—';
    return `<tr data-id="${t.id}">
      <td><input type="checkbox" class="row-check" data-id="${t.id}" ${checked}></td>
      <td class="mono">${esc(t.hardware_id)}</td>
      <td>${esc(t.device_model || '—')}</td>
      <td><span class="chip">${esc(displayStatus(t))}</span></td>
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
