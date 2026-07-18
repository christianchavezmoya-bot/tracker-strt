/**
 * HOLO-RTLS — Dashboard JS
 * Command center: SSE live updates, tag list, alert feed, map integration.
 */
let trackers = {};          // tracker_id → tracker object (updated live)
let trackerList = [];       // ordered list for rendering
let alerts = [];
let nodes = [];
let selectedTrackerId = null;
let currentView = '2d';
let filters = { people: true, machines: true, sensors: true, offline: true, alerts: true };

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  if (!API.isLoggedIn()) {
    window.location.href = '/login';
    return;
  }
  await loadUserInfo();
  await Promise.all([loadTrackers(), loadAlerts(), loadNodes(), loadZones()]);
  updateStats();
  initMap2D();
  initMap3D();
  startSSE();
  setupKeyboardShortcuts();
});

// ── Auth / User ──────────────────────────────────────────────────────────────
async function loadUserInfo() {
  const res = await API.get('/auth/me');
  const data = await API.json(res);
  if (!res || !res.ok) { window.location.href = '/login'; return; }
  const user = data.user;
  document.getElementById('userName').textContent = user.display_name || user.username;
  document.getElementById('userAvatar').textContent =
    (user.display_name || user.username).charAt(0).toUpperCase();
  if (user.role === 'ADMIN') {
    document.getElementById('menuUsers').style.display = 'flex';
    document.getElementById('menuAudit').style.display = 'flex';
  }
}

function toggleUserMenu() {
  document.getElementById('userDropdown').classList.toggle('open');
}
document.addEventListener('click', e => {
  if (!e.target.closest('.user-menu')) {
    document.getElementById('userDropdown')?.classList.remove('open');
  }
});

// ── Load data ──────────────────────────────────────────────────────────────────
async function loadTrackers() {
  // Load both tracker metadata and live positions in parallel
  const [metaRes, posRes] = await Promise.all([
    API.get('/trackers'),
    API.get('/positioning/live'),
  ]);
  const metaData = await API.json(metaRes);
  const posData = await API.json(posRes);

  if (metaData && metaData.items) {
    // Index by id, merge with live position
    const positions = {};
    if (posData && posData.positions) {
      posData.positions.forEach(p => { positions[p.tracker_id] = p; });
    }
    metaData.items.forEach(t => {
      const pos = positions[t.id] || {};
      trackers[t.id] = {
        ...t,
        pos_x: pos.x ?? t.pos_x,
        pos_y: pos.y ?? t.pos_y,
        pos_z: pos.z ?? t.pos_z,
        last_seen: pos.last_seen_hardware || pos.updated_at || null,
        speed: pos.speed ?? null,
        source: pos.source ?? null,
      };
    });
  }
  trackerList = Object.values(trackers);
  renderTagList();
  updateStats();
  if (window.renderTrackerDots) window.renderTrackerDots();
}

async function loadAlerts() {
  const res = await API.get('/alerts/active');
  const data = await API.json(res);
  if (!res || !res.ok) return;
  alerts = data.items || [];
  renderAlertFeed();
  const badge = document.getElementById('alertBadge');
  const count = alerts.length;
  if (count > 0) {
    badge.textContent = count > 99 ? '99+' : count;
    badge.style.display = 'inline';
  } else {
    badge.style.display = 'none';
  }
}

async function loadNodes() {
  const res = await API.get('/nodes');
  const data = await API.json(res);
  if (!res || !res.ok) return;
  nodes = data.items || [];
  document.getElementById('statNodes').textContent = nodes.length;
}

async function loadZones() {
  // Zones are loaded by map2d.js / map3d.js
}

// ── Tag List ─────────────────────────────────────────────────────────────────
function renderTagList() {
  const list = document.getElementById('tagList');
  const filtered = trackerList.filter(t => {
    if (t.category === 'PERSONNEL_TAG' && !filters.people) return false;
    if (t.category === 'MACHINE_TAG' && !filters.machines) return false;
    if (t.category === 'ENV_SENSOR' && !filters.sensors) return false;
    if (t.asset_state === 'OFFLINE' && !filters.offline) return false;
    if (t.alert_status !== 'NORMAL' && !filters.alerts) return false;
    return true;
  });
  document.getElementById('filterCount').textContent = filtered.length;

  if (filtered.length === 0) {
    list.innerHTML = '<div class="tag-loading">No assets match filters</div>';
    return;
  }
  list.innerHTML = filtered.map(t => {
    const dotClass = alertDotClass(t.alert_status, t.asset_state);
    const badgeClass = alertBadgeClass(t.alert_status);
    const lastSeen = t.last_seen ? timeAgo(t.last_seen) : '—';
    return `
    <div class="tag-item ${selectedTrackerId === t.id ? 'selected' : ''}"
         onclick="selectTracker(${t.id})" data-id="${t.id}">
      <div class="tag-item-dot ${dotClass}"></div>
      <div class="tag-item-info">
        <div class="tag-item-name">${t.assigned_name || t.hardware_id || '—'}</div>
        <div class="tag-item-meta">
          ${t.current_section || t.section_name || '—'}
          · ${t.battery_level !== undefined ? Math.round(t.battery_level) + '%' : ''}
          ${t.speed !== null ? '· ' + t.speed.toFixed(1) + 'm/s' : ''}
        </div>
        <div class="tag-item-time">${lastSeen}</div>
      </div>
      ${t.alert_status !== 'NORMAL' ? `<span class="tag-item-badge ${badgeClass}">${t.alert_status.replace('_',' ')}</span>` : ''}
    </div>`;
  }).join('');
}

function alertDotClass(status, state) {
  if (state === 'OFFLINE' || state === 'DECOMMISSIONED') return 'dot-gray';
  if (status === 'NORMAL') return 'dot-green';
  if (status === 'RESTRICTED_ZONE' || status === 'CRITICAL_VITALS') return 'dot-red';
  return 'dot-yellow';
}

function alertBadgeClass(status) {
  if (status === 'RESTRICTED_ZONE' || status === 'CRITICAL_VITALS') return 'badge-red';
  return 'badge-yellow';
}

// ── Alert Feed ──────────────────────────────────────────────────────────────
function renderAlertFeed() {
  const list = document.getElementById('alertList');
  const empty = document.getElementById('alertEmpty');
  document.getElementById('alertCountBadge').textContent = alerts.length;
  if (alerts.length === 0) {
    if (empty) empty.style.display = 'flex';
    return;
  }
  if (empty) empty.style.display = 'none';
  // Remove the empty div from list if it exists
  const emptyEl = list.querySelector('.alert-empty');
  if (emptyEl) emptyEl.style.display = 'none';

  // Only show first 10 in sidebar
  const shown = alerts.slice(0, 10);
  list.innerHTML = shown.map(a => `
    <div class="alert-item" onclick="zoomToAlert(${a.id})">
      <div class="alert-item-header">
        <div class="alert-item-dot ${a.alert_type === 'RESTRICTED_ZONE' || a.alert_type === 'NO_SIGNAL' ? 'dot-red' : 'dot-yellow'}"></div>
        <span class="alert-item-type ${a.alert_type === 'RESTRICTED_ZONE' || a.alert_type === 'NO_SIGNAL' ? 'red' : 'yellow'}">${a.alert_type.replace('_',' ')}</span>
        <span class="alert-item-time">${timeAgo(a.triggered_at)}</span>
      </div>
      <div class="alert-item-body">${a.message || a.alert_type} — ${a.section_name || 'Unknown section'}</div>
      ${a.state === 'ACTIVE' ? `<button class="alert-ack-btn" onclick="event.stopPropagation();acknowledgeAlert(${a.id})">Ack</button>` : ''}
    </div>`).join('');
}

async function acknowledgeAlert(alertId) {
  event.stopPropagation();
  const res = await API.post(`/alerts/${alertId}/acknowledge`);
  if (res && res.ok) await loadAlerts();
}

// ── Tracker Selection ────────────────────────────────────────────────────────
function selectTracker(id) {
  selectedTrackerId = id;
  renderTagList();
  const t = trackers[id];
  if (!t) return;
  showTagCard(t);
  if (t.pos_x !== undefined) {
    if (currentView === '2d' && window.zoomToPosition) window.zoomToPosition(t.pos_x, t.pos_y);
    if (currentView === '3d' && window.focus3DTracker) window.focus3DTracker(id);
  }
}

function showTagCard(t) {
  const card = document.getElementById('tagCard');
  const dotEl = document.getElementById('tagCardDot');
  dotEl.className = `tag-card-dot ${alertDotClass(t.alert_status, t.asset_state)}`;
  document.getElementById('tagCardName').textContent = t.assigned_name || t.hardware_id || '—';
  document.getElementById('tagCardType').textContent = t.category || '—';
  document.getElementById('tagCardHardwareId').textContent = t.hardware_id || '—';
  document.getElementById('tagCardSection').textContent = t.current_section || t.section_name || '—';

  // Battery
  const battEl = document.getElementById('tagCardBattery');
  if (t.battery_level !== undefined) {
    battEl.textContent = Math.round(t.battery_level) + '%';
    battEl.style.color = t.battery_level < 20 ? 'var(--red)' : 'var(--text-primary)';
  } else {
    battEl.textContent = '—';
  }

  // Position
  if (t.pos_x !== undefined) {
    document.getElementById('tagCardPosition').textContent =
      `x=${t.pos_x.toFixed(2)} y=${t.pos_y.toFixed(2)} z=${(t.pos_z || 0).toFixed(2)}`;
  } else {
    document.getElementById('tagCardPosition').textContent = '—';
  }

  document.getElementById('tagCardLastSeen').textContent = t.last_seen ? timeAgo(t.last_seen) : '—';

  // Speed
  const speedRow = document.getElementById('tagCardSpeedRow');
  if (t.speed !== null && t.speed !== undefined) {
    speedRow.style.display = 'flex';
    document.getElementById('tagCardSpeed').textContent = t.speed.toFixed(2) + ' m/s';
  } else {
    speedRow.style.display = 'none';
  }

  card.style.display = 'block';
}

function closeTagCard() {
  document.getElementById('tagCard').style.display = 'none';
  selectedTrackerId = null;
  renderTagList();
}

// ── Filters ──────────────────────────────────────────────────────────────────
function toggleFilter(type) {
  const map = { all: null, people: 'people', machines: 'machines', sensors: 'sensors',
                offline: 'offline', alerts: 'alerts' };
  const key = map[type];
  if (!key) return;
  const checkbox = document.getElementById(`filter${type.charAt(0).toUpperCase() + type.slice(1)}`);
  if (checkbox) filters[key] = checkbox.checked;
  renderTagList();
}

// ── Stats ─────────────────────────────────────────────────────────────────────
function updateStats() {
  const all = trackerList;
  document.getElementById('statActive').textContent =
    all.filter(t => t.asset_state === 'ACTIVE').length;
  document.getElementById('statAlerts').textContent = alerts.length;
  document.getElementById('statCheckedIn').textContent =
    all.filter(t => t.check_status === 'CHECKED_IN').length;
}

// ── View Toggle ──────────────────────────────────────────────────────────────
function setView(view) {
  currentView = view;
  document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
  document.querySelector(`.view-btn[data-view="${view}"]`).classList.add('active');
  document.getElementById('map2d').style.display = view === '2d' ? 'block' : 'none';
  document.getElementById('map3d').style.display = view === '3d' ? 'block' : 'none';
  // Trigger map resize / re-render
  if (view === '2d' && window._map2d) window._map2d.invalidateSize();
  if (view === '3d' && window.render3DTrackerDots) window.render3DTrackerDots();
}

// ── Map tools ─────────────────────────────────────────────────────────────────
function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen();
  } else {
    document.exitFullscreen();
  }
}
function resetCamera() {
  if (currentView === '2d' && window._map2d) {
    window._map2d.setView([0, 0], 16);
  }
}
function toggleHeatmap() {
  // Toggle heatmap layer visibility
  if (window._heatmapLayer) {
    const m = window._map2d;
    if (m.hasLayer(window._heatmapLayer)) {
      m.removeLayer(window._heatmapLayer);
    } else {
      window._heatmapLayer.addTo(m);
    }
  }
}
function toggleLayers() {
  // Show layer control
}
function triggerAlarm() {
  // TODO: downlink alarm via MQTT
  alert('Alarm triggered for tracker');
}
function editTag() {
  window.location.href = `/trackers?id=${selectedTrackerId}`;
}

// ── Zoom to alert ───────────────────────────────────────────────────────────
function zoomToAlert(alertId) {
  const a = alerts.find(x => x.id === alertId);
  if (!a) return;
  if (a.tracker_id && trackers[a.tracker_id]) {
    selectTracker(a.tracker_id);
  }
}

// ── SSE Stream ──────────────────────────────────────────────────────────────
let es = null;
let esRetryTimer = null;

function startSSE() {
  if (es) { try { es.close(); } catch {} }
  es = new EventSource('/api/stream/positions');

  es.addEventListener('position_update', e => {
    const data = JSON.parse(e.data);
    handlePositionUpdate(data);
  });

  es.addEventListener('snapshot', e => {
    const data = JSON.parse(e.data);
    if (data.positions) {
      data.positions.forEach(pos => {
        const tid = pos.tracker_id;
        if (trackers[tid]) {
          trackers[tid].pos_x = pos.x;
          trackers[tid].pos_y = pos.y;
          trackers[tid].pos_z = pos.z;
          trackers[tid].accuracy = pos.accuracy;
          trackers[tid].vx = pos.vx;
          trackers[tid].vy = pos.vy;
          trackers[tid].speed = pos.speed;
          trackers[tid].last_seen = pos.timestamp;
          trackers[tid].source = pos.source;
        }
      });
      trackerList = Object.values(trackers);
      if (window.renderTrackerDots) window.renderTrackerDots();
      updateStats();
    }
  });

  es.addEventListener('alert', e => {
    const data = JSON.parse(e.data);
    const alert = data.alert;
    // Add to alerts if not already there
    if (!alerts.find(a => a.id === alert.id)) {
      alerts.unshift(alert);
      renderAlertFeed();
    }
    // Badge
    const badge = document.getElementById('alertBadge');
    const count = alerts.filter(a => a.state === 'ACTIVE').length;
    if (count > 0) {
      badge.textContent = count > 99 ? '99+' : count;
      badge.style.display = 'inline';
    }
    showAlertToast(alert);
  });

  es.addEventListener('alert_acknowledged', e => {
    const data = JSON.parse(e.data);
    const alert = data.alert;
    const idx = alerts.findIndex(a => a.id === alert.id);
    if (idx >= 0) alerts[idx] = alert;
    renderAlertFeed();
  });

  es.addEventListener('heartbeat', () => {
    updateStatusIndicator(true);
  });

  es.onerror = () => {
    updateStatusIndicator(false);
    es.close();
    esRetryTimer = setTimeout(startSSE, 5000);
  };
}

function handlePositionUpdate(data) {
  const tid = data.tracker_id;
  if (!trackers[tid]) return;  // Unknown tracker
  trackers[tid].pos_x = data.x;
  trackers[tid].pos_y = data.y;
  trackers[tid].pos_z = data.z;
  trackers[tid].accuracy = data.accuracy;
  trackers[tid].vx = data.vx;
  trackers[tid].vy = data.vy;
  trackers[tid].speed = data.speed;
  trackers[tid].last_seen = data.timestamp;
  trackers[tid].source = data.source;

  // Update tag card if this tracker is selected
  if (selectedTrackerId === tid) {
    showTagCard(trackers[tid]);
  }

  // Re-render tag list row (just update time / speed, don't re-render whole list)
  const row = document.querySelector(`.tag-item[data-id="${tid}"]`);
  if (row) {
    const timeEl = row.querySelector('.tag-item-time');
    if (timeEl) timeEl.textContent = timeAgo(data.timestamp);
    const metaEl = row.querySelector('.tag-item-meta');
    if (metaEl && data.speed !== null) {
      const section = trackers[tid].current_section || '—';
      const batt = trackers[tid].battery_level !== undefined ? Math.round(trackers[tid].battery_level) + '%' : '';
      metaEl.textContent = `${section} ${batt ? '· ' + batt : ''} · ${data.speed.toFixed(1)}m/s`;
    }
  }

  // Update map dots (both 2D and 3D)
  if (window.updateTrackerDot) window.updateTrackerDot(tid, data);
  if (window.updateTrackerDot3D) window.updateTrackerDot3D(tid, data);
  updateStats();
}

function showAlertToast(alert) {
  const toast = document.createElement('div');
  toast.style.cssText = `
    position: fixed; bottom: 20px; right: 20px; z-index: 9999;
    background: rgba(255,68,68,0.1); border: 1px solid var(--red);
    border-radius: var(--radius); padding: 14px 18px; max-width: 320px;
    backdrop-filter: blur(8px); box-shadow: 0 8px 24px rgba(0,0,0,0.5);
    animation: slideUp 0.3s ease;
  `;
  toast.innerHTML = `
    <div style="font-size:10px;font-weight:700;color:var(--red);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:5px">
      ⚠️ ${alert.alert_type.replace(/_/g,' ')}
    </div>
    <div style="font-size:13px;color:var(--text-primary)">${alert.message || 'Alert triggered'}</div>
    <div style="font-size:11px;color:var(--text-muted);margin-top:5px">${timeAgo(alert.triggered_at)}</div>`;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, 8000);
}

function updateStatusIndicator(connected) {
  const dot = document.getElementById('statusDot');
  const text = document.getElementById('statusText');
  if (!dot || !text) return;
  if (connected) {
    dot.style.background = 'var(--green)';
    dot.style.boxShadow = '0 0 6px var(--green)';
    text.textContent = 'Live';
  } else {
    dot.style.background = 'var(--yellow)';
    dot.style.boxShadow = '0 0 6px var(--yellow)';
    text.textContent = 'Reconnecting...';
  }
}

// ── History Playback ─────────────────────────────────────────────────────────
let historyMode = false;
let historyData = [];
let historyIndex = 0;

async function viewHistory() {
  if (!selectedTrackerId) return;
  document.getElementById('historyBar').style.display = 'flex';
  const res = await API.get(`/positioning/history/${selectedTrackerId}?limit=500`);
  const data = await API.json(res);
  if (!res || !res.ok || !data.history) return;
  historyData = data.history.reverse();  // oldest first
  historyIndex = historyData.length - 1;  // start at newest

  const slider = document.getElementById('historySlider');
  slider.max = historyData.length - 1;
  slider.value = historyIndex;
  updateHistoryFrame();

  document.getElementById('historyStartTime').textContent =
    historyData[0] ? timeAgo(historyData[0].timestamp) : '—';
}

function updateHistoryFrame() {
  const frame = historyData[historyIndex];
  if (!frame) return;
  // Update tag card
  if (selectedTrackerId && trackers[selectedTrackerId]) {
    const t = trackers[selectedTrackerId];
    document.getElementById('tagCardPosition').textContent =
      `x=${frame.x.toFixed(2)} y=${frame.y.toFixed(2)} z=${(frame.z||0).toFixed(2)}`;
    document.getElementById('tagCardLastSeen').textContent = timeAgo(frame.timestamp);
  }
  // Update map dot
  if (window.updateTrackerDot) {
    window.updateTrackerDot(selectedTrackerId, frame);
  }
  // Update time display
  const timeEl = document.getElementById('historyTimeDisplay');
  if (timeEl) timeEl.textContent = frame.timestamp ? new Date(frame.timestamp).toLocaleTimeString() : '—';
}

document.addEventListener('DOMContentLoaded', () => {
  const slider = document.getElementById('historySlider');
  if (slider) {
    slider.addEventListener('input', () => {
      historyIndex = parseInt(slider.value);
      updateHistoryFrame();
    });
  }
});

function closeHistory() {
  document.getElementById('historyBar').style.display = 'none';
  historyMode = false;
  historyData = [];
  // Restore live positions
  if (selectedTrackerId && trackers[selectedTrackerId]) {
    const t = trackers[selectedTrackerId];
    if (window.updateTrackerDot) window.updateTrackerDot(selectedTrackerId, { x: t.pos_x, y: t.pos_y, z: t.pos_z });
    showTagCard(t);
  }
}

// ── Notifications ────────────────────────────────────────────────────────────
function toggleNotifications() {
  const dropdown = document.getElementById('notifDropdown');
  const isOpen = dropdown.style.display !== 'none';
  dropdown.style.display = isOpen ? 'none' : 'block';
  if (!isOpen) loadNotifications();
}
document.addEventListener('click', e => {
  if (!e.target.closest('#notifBtn') && !e.target.closest('.notifications-dropdown')) {
    const d = document.getElementById('notifDropdown');
    if (d) d.style.display = 'none';
  }
});

async function loadNotifications() {
  const res = await API.get('/alerts/notifications');
  const data = await API.json(res);
  if (!res || !res.ok) return;
  const list = document.getElementById('notifList');
  if (!data.items || data.items.length === 0) {
    list.innerHTML = '<div class="notif-empty">No new notifications</div>';
    return;
  }
  list.innerHTML = data.items.map(n => `
    <div class="notif-item ${n.is_read ? '' : 'unread'}" onclick="markRead(${n.id})">
      <div class="notif-title">${n.title}</div>
      <div class="notif-body">${n.message || ''}</div>
      <div class="notif-time">${timeAgo(n.created_at)}</div>
    </div>`).join('');
}

async function markRead(id) {
  await API.post(`/alerts/notifications/${id}/read`, {});
  loadNotifications();
}

async function markAllRead() {
  await API.post('/alerts/notifications/read-all', {});
  loadNotifications();
}

// ── Search ──────────────────────────────────────────────────────────────────
function openSearch() {
  document.getElementById('searchModal').style.display = 'flex';
  document.getElementById('searchInput').focus();
}
function closeSearch() {
  document.getElementById('searchModal').style.display = 'none';
  document.getElementById('searchInput').value = '';
  document.getElementById('searchResults').innerHTML = '<div class="search-hint">Type to search...</div>';
}
async function doSearch() {
  const q = document.getElementById('searchInput').value.trim();
  if (q.length < 2) return;
  const res = await API.get(`/search?q=${encodeURIComponent(q)}`);
  const data = await API.json(res);
  if (!res || !res.ok || !data.results) return;
  const { trackers: ts, users } = data.results;
  const all = [
    ...(ts || []).map(t => ({ type: 'tracker', name: t.assigned_name || t.hardware_id,
      meta: t.category, id: t.id })),
    ...(users || []).map(u => ({ type: 'user', name: u.display_name || u.username,
      meta: u.role, id: u.id })),
  ];
  if (!all.length) {
    document.getElementById('searchResults').innerHTML = '<div class="search-hint">No results</div>';
    return;
  }
  document.getElementById('searchResults').innerHTML = all.map(item => `
    <div class="search-result-item" onclick="onSearchResult('${item.type}',${item.id})">
      <i class="fa-solid ${item.type === 'tracker' ? 'fa-signal' : 'fa-user'}"></i>
      <div>
        <div class="search-result-name">${item.name}</div>
        <div class="search-result-meta">${item.meta} · ${item.type}</div>
      </div>
    </div>`).join('');
}
function onSearchResult(type, id) {
  closeSearch();
  if (type === 'tracker') selectTracker(id);
}

// ── Keyboard shortcuts ───────────────────────────────────────────────────────
function setupKeyboardShortcuts() {
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault(); openSearch();
    }
    if (e.key === 'Escape') {
      closeSearch();
      closeTagCard();
      closeHistory();
    }
  });
}

// ── Helpers ─────────────────────────────────────────────────────────────────
function timeAgo(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 5) return 'just now';
  if (diff < 60) return Math.floor(diff) + 's ago';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return d.toLocaleDateString();
}
