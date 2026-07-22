/**
 * HOLO-RTLS — Anchors commission: scan, acknowledge, map pick, timeline.
 */
'use strict';

let commissionScanTimer = null;
let commissionScanSec = 60;
let commissionView = 'table';
let commissionScanCache = [];
let commissionSelectedId = null;
let commissionMap = null;
let commissionPickMarker = null;
let commissionInited = false;

function fmtNodeTime(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  } catch (_) { return '—'; }
}

function nodeTooltip(item) {
  return [
    `ID: ${item.mac_address}`,
    item.strata_node_id ? `STRATA: ${item.strata_node_id}` : '',
    item.node_ip && item.node_ip !== '—' ? `IP: ${item.node_ip}` : '',
    item.last_topic ? `Topic: ${item.last_topic}` : '',
    item.payload_format ? `Format: ${item.payload_format}` : '',
    item.last_heard_at ? `Last heard: ${fmtNodeTime(item.last_heard_at)}` : '',
    item.placed_on_map ? 'Placed on map' : 'Not placed',
  ].filter(Boolean).join('\n');
}

function statePill(state) {
  const map = {
    detected: ['pill-yellow', 'Detected'],
    awaiting_placement: ['pill-yellow', 'Awaiting placement'],
    active: ['pill-green', 'Active'],
    inactive: ['pill-gray', 'Inactive'],
    decommissioned: ['pill-red', 'Decommissioned'],
    manual: ['pill-gray', 'Manual'],
  };
  const [cls, label] = map[state] || ['pill-gray', state || '—'];
  return `<span class="status-pill ${cls}"><span class="status-dot-sm"></span>${label}</span>`;
}

async function runCommissionScan() {
  const btn = document.getElementById('btnCommissionRefresh');
  if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Scanning…'; }
  try {
    const res = await API.post('/nodes/scan/run', {});
    const data = await API.json(res);
    if (res && res.ok) {
      commissionScanCache = data.items || [];
      renderCommissionTable();
      renderCommissionStats(data);
      if (commissionView === 'timeline') loadNodeTimelineChart();
      if (typeof loadAllNodes === 'function') await loadAllNodes();
      if (typeof renderSummary === 'function') renderSummary();
    }
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-rotate"></i> Refresh'; }
  }
}

function renderCommissionStats(data) {
  const el = document.getElementById('commissionScanSummary');
  if (!el) return;
  const items = data.items || [];
  const online = items.filter(i => i.online).length;
  el.textContent = `${items.length} anchors · ${online} online · scanned ${fmtNodeTime(data.scanned_at)}`;
}

function renderCommissionTable() {
  const tbody = document.getElementById('commissionScanBody');
  if (!tbody) return;
  if (!commissionScanCache.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="table-empty">No anchors detected — turn on MQTT receiver and power on WiFi units.</td></tr>';
    return;
  }
  tbody.innerHTML = commissionScanCache.map(item => {
    const name = item.name || item.mac_address;
    const ip = item.node_ip || '—';
    const title = nodeTooltip(item).replace(/"/g, '&quot;').replace(/\n/g, '&#10;');
    return `<tr class="${commissionSelectedId === item.node_id ? 'row-selected' : ''}" onclick="selectCommissionNode(${item.node_id})">
      <td title="${title}"><strong>${name}</strong></td>
      <td class="mono" title="${title}">${ip}</td>
      <td title="${title}">${fmtNodeTime(item.last_heard_at)}</td>
      <td>${statePill(item.commission_state)}</td>
      <td>${item.online ? '<span style="color:var(--green)">Online</span>' : '<span style="color:var(--text-muted)">Offline</span>'}</td>
      <td>
        <button class="action-btn" title="Configure" onclick="event.stopPropagation();selectCommissionNode(${item.node_id})"><i class="fa-solid fa-sliders"></i></button>
      </td>
    </tr>`;
  }).join('');
}

function selectCommissionNode(id) {
  commissionSelectedId = id;
  renderCommissionTable();
  const item = commissionScanCache.find(n => n.node_id === id);
  if (!item) return;
  const panel = document.getElementById('commissionConfigPanel');
  if (!panel) return;
  panel.style.display = 'block';
  document.getElementById('commissionConfigTitle').textContent = item.name || item.mac_address;
  document.getElementById('commissionNodeName').value = item.name && !item.name.startsWith('STRATA-') ? item.name : '';
  document.getElementById('commissionNodeIp').value = item.node_ip && item.node_ip !== '—' ? item.node_ip : '';
  document.getElementById('commissionNodeX').value = item.pos_x || 0;
  document.getElementById('commissionNodeY').value = item.pos_y || 0;
  document.getElementById('commissionNodeZ').value = item.pos_z || 0;
  document.getElementById('commissionMetaId').textContent = item.mac_address;
  document.getElementById('commissionMetaStrata').textContent = item.strata_node_id || '—';
  document.getElementById('commissionAckBtn').style.display = item.mqtt_acknowledged ? 'none' : 'inline-flex';
  document.getElementById('commissionActivateBtn').style.display = 'inline-flex';
}

async function acknowledgeCommissionNode() {
  if (!commissionSelectedId) return;
  const name = document.getElementById('commissionNodeName').value.trim();
  const ip = document.getElementById('commissionNodeIp').value.trim();
  const res = await API.post(`/nodes/${commissionSelectedId}/acknowledge`, {
    assigned_name: name || undefined,
    node_ip: ip || undefined,
  });
  if (res && res.ok) {
    showToast?.('Anchor acknowledged', 'success');
    await runCommissionScan();
    selectCommissionNode(commissionSelectedId);
  } else showToast?.('Acknowledge failed', 'error');
}

async function activateCommissionNode() {
  if (!commissionSelectedId) return;
  const body = {
    assigned_name: document.getElementById('commissionNodeName').value.trim(),
    node_ip: document.getElementById('commissionNodeIp').value.trim(),
    pos_x: parseFloat(document.getElementById('commissionNodeX').value) || 0,
    pos_y: parseFloat(document.getElementById('commissionNodeY').value) || 0,
    pos_z: parseFloat(document.getElementById('commissionNodeZ').value) || 0,
  };
  if (!body.assigned_name) { showToast?.('Enter anchor name', 'warning'); return; }
  if (!body.pos_x && !body.pos_y) { showToast?.('Pick a map location or enter coordinates', 'warning'); return; }
  const res = await API.post(`/nodes/${commissionSelectedId}/activate`, body);
  if (res && res.ok) {
    showToast?.('Anchor saved and activated', 'success');
    await runCommissionScan();
    if (window.refreshRtlsSetupUi) refreshRtlsSetupUi();
  } else showToast?.('Save failed', 'error');
}

async function decommissionCommissionNode() {
  if (!commissionSelectedId) return;
  if (!(await holoConfirm?.('Decommission this anchor? It will be hidden from the live map.', { danger: true }))) return;
  const res = await API.post(`/nodes/${commissionSelectedId}/decommission`, {});
  if (res && res.ok) { showToast?.('Anchor decommissioned', 'info'); await runCommissionScan(); }
}

async function inactiveCommissionNode() {
  if (!commissionSelectedId) return;
  const res = await API.post(`/nodes/${commissionSelectedId}/inactive`, {});
  if (res && res.ok) { showToast?.('Anchor set inactive', 'info'); await runCommissionScan(); }
}

async function purgeCommissionNode() {
  if (!commissionSelectedId) return;
  if (!(await holoConfirm?.('Permanently delete this anchor?', { danger: true }))) return;
  const res = await API.delete(`/nodes/${commissionSelectedId}`);
  if (res && res.ok) {
    showToast?.('Anchor purged', 'success');
    commissionSelectedId = null;
    document.getElementById('commissionConfigPanel').style.display = 'none';
    await runCommissionScan();
  }
}

function scheduleCommissionScan() {
  clearInterval(commissionScanTimer);
  const sel = document.getElementById('commissionScanInterval');
  commissionScanSec = parseInt(sel?.value || '60', 10);
  commissionScanTimer = setInterval(runCommissionScan, commissionScanSec * 1000);
}

function setCommissionView(mode) {
  commissionView = mode;
  const table = document.getElementById('commissionTablePanel');
  const chart = document.getElementById('commissionChartPanel');
  document.getElementById('commissionTableBtn')?.classList.toggle('active', mode === 'table');
  document.getElementById('commissionChartBtn')?.classList.toggle('active', mode === 'timeline');
  if (table) table.style.display = mode === 'table' ? 'block' : 'none';
  if (chart) chart.style.display = mode === 'timeline' ? 'block' : 'none';
  if (mode === 'timeline') loadNodeTimelineChart();
}

async function loadNodeTimelineChart() {
  const win = document.getElementById('commissionChartWindow');
  const minutes = parseInt(win?.value || '60', 10);
  const res = await API.get(`/nodes/presence/timeline?minutes=${minutes}`);
  const data = await API.json(res);
  if (res && res.ok) drawNodeTimelineChart(data);
}

function rssiToY(rssi, rowTop, rowH) {
  const clamped = Math.max(-100, Math.min(-40, rssi));
  return rowTop + rowH - ((clamped + 100) / 60) * rowH * 0.85 - rowH * 0.05;
}

function drawNodeTimelineChart(data) {
  const canvas = document.getElementById('commissionTimelineCanvas');
  if (!canvas) return;
  const nodes = data.nodes || [];
  const rowH = 56;
  const padL = 200;
  const padR = 48;
  const padT = 28;
  const padB = 36;
  const width = Math.max(720, canvas.parentElement?.clientWidth - 24 || 720);
  const height = Math.max(180, padT + padB + nodes.length * rowH);
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#0a0e14';
  ctx.fillRect(0, 0, width, height);
  const now = Date.now();
  const windowMs = (data.window_minutes || 60) * 60 * 1000;
  const t0 = now - windowMs;
  const plotW = width - padL - padR;

  if (!nodes.length) {
    ctx.fillStyle = '#64748b';
    ctx.font = '12px system-ui';
    ctx.fillText('No timeline data yet — anchors will appear after MQTT traffic.', padL, padT + 30);
    return;
  }

  nodes.forEach((nd, idx) => {
    const rowTop = padT + idx * rowH;
    ctx.fillStyle = '#e2e8f0';
    ctx.font = '11px system-ui,sans-serif';
    const label = (nd.label || nd.mac_address || '').slice(0, 22);
    ctx.fillText(label, 8, rowTop + rowH * 0.45);
    ctx.fillStyle = '#64748b';
    ctx.font = '10px monospace';
    ctx.fillText(nd.node_ip || '—', 8, rowTop + rowH * 0.75);
    const samples = nd.samples || [];
    let lastX = padL;
    samples.forEach(s => {
      const x = padL + ((new Date(s.timestamp).getTime() - t0) / windowMs) * plotW;
      if (!s.online) {
        ctx.fillStyle = 'rgba(255,68,68,.7)';
        ctx.fillRect(x - 1, rowTop + 4, 3, rowH - 8);
      }
      if (s.rssi != null) {
        const y = rssiToY(s.rssi, rowTop, rowH);
        ctx.strokeStyle = '#6bff47';
        ctx.beginPath();
        ctx.moveTo(lastX, y);
        ctx.lineTo(x, y);
        ctx.stroke();
      }
      lastX = x;
    });
  });
}

async function openCommissionMapPick() {
  const modal = document.getElementById('commissionMapModal');
  if (!modal) return;
  modal.style.display = 'flex';
  setTimeout(initCommissionMapPicker, 100);
}

function closeCommissionMapPick() {
  document.getElementById('commissionMapModal').style.display = 'none';
  if (commissionMap) {
    try { commissionMap.remove(); } catch (_) {}
    commissionMap = null;
  }
}

async function initCommissionMapPicker() {
  const el = document.getElementById('commissionMap2d');
  if (!el || commissionMap) return;
  if (typeof L === 'undefined') return;
  let cal = null;
  try {
    const res = await API.get('/positioning/calibration');
    cal = await API.json(res);
  } catch (_) {}
  const b = cal?.bounds || { minX: 0, maxX: 50, minY: 0, maxY: 50 };
  const spanX = Math.max(1, b.maxX - b.minX);
  const spanY = Math.max(1, b.maxY - b.minY);
  commissionMap = L.map(el, { crs: L.CRS.Simple, minZoom: -2, maxZoom: 4, zoomControl: true });
  const bounds = [[b.minY, b.minX], [b.maxY, b.maxX]];
  commissionMap.fitBounds(bounds);
  el.classList.add('commission-pick-cursor');
  commissionMap.on('click', e => {
    const lat = e.latlng.lat;
    const lng = e.latlng.lng;
    document.getElementById('commissionNodeX').value = Number(lng).toFixed(2);
    document.getElementById('commissionNodeY').value = Number(lat).toFixed(2);
    if (commissionPickMarker) commissionMap.removeLayer(commissionPickMarker);
    commissionPickMarker = L.circleMarker(e.latlng, { radius: 8, color: '#00e5ff', fillColor: '#00e5ff', fillOpacity: 0.8 });
    commissionPickMarker.addTo(commissionMap);
    document.getElementById('commissionCoordPreview').textContent = `X=${lng.toFixed(1)}  Y=${lat.toFixed(1)}`;
  });
}

function initCommissionTab() {
  if (commissionInited) return;
  commissionInited = true;
  const interval = document.getElementById('commissionScanInterval');
  if (interval) interval.addEventListener('change', scheduleCommissionScan);
  scheduleCommissionScan();
  runCommissionScan();
}

window.runCommissionScan = runCommissionScan;
window.selectCommissionNode = selectCommissionNode;
window.acknowledgeCommissionNode = acknowledgeCommissionNode;
window.activateCommissionNode = activateCommissionNode;
window.decommissionCommissionNode = decommissionCommissionNode;
window.inactiveCommissionNode = inactiveCommissionNode;
window.purgeCommissionNode = purgeCommissionNode;
window.setCommissionView = setCommissionView;
window.openCommissionMapPick = openCommissionMapPick;
window.closeCommissionMapPick = closeCommissionMapPick;
window.loadNodeTimelineChart = loadNodeTimelineChart;
window.initCommissionTab = initCommissionTab;
