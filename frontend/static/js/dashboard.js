/**
 * HOLO-RTLS — Dashboard JS
 * Main command center logic: auth check, tag list, alert feed, SSE stream.
 */

let trackers = [];
let alerts = [];
let nodes = [];
let selectedTrackerId = null;
let currentView = '2d';
let filters = { people: true, machines: true, sensors: true, offline: true, alerts: true };
let map2d = null;
let map3d = null;

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  if (!API.isLoggedIn()) {
    window.location.href = '/login';
    return;
  }
  await loadUserInfo();
  await Promise.all([loadTrackers(), loadAlerts(), loadNodes()]);
  updateStats();
  initMap2D();
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
  document.getElementById('userAvatar').textContent = (user.display_name || user.username).charAt(0).toUpperCase();
  // Show admin-only menu items
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

// ── Load data ─────────────────────────────────────────────────────────────────
async function loadTrackers() {
  const res = await API.get('/trackers');
  const data = await API.json(res);
  if (res && res.ok) {
    trackers = data.items || [];
    renderTagList();
    updateStats();
  }
}

async function loadAlerts() {
  const res = await API.get('/alerts/active');
  const data = await API.json(res);
  if (res && res.ok) {
    alerts = data.items || [];
    renderAlertFeed();
    const badge = document.getElementById('alertBadge');
    const count = alerts.length;
    if (count > 0) {
      badge.textContent = count; badge.style.display = 'inline';
    } else {
      badge.style.display = 'none';
    }
  }
}

async function loadNodes() {
  const res = await API.get('/nodes');
  const data = await API.json(res);
  if (res && res.ok) {
    nodes = data.items || [];
    document.getElementById('statNodes').textContent = nodes.length;
  }
}

// ── Render Tag List ───────────────────────────────────────────────────────────
function renderTagList() {
  const list = document.getElementById('tagList');
  const filtered = trackers.filter(t => {
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
    return `
      <div class="tag-item ${selectedTrackerId === t.id ? 'selected' : ''}"
           onclick="selectTracker(${t.id})" data-id="${t.id}">
        <div class="tag-item-dot ${dotClass}"></div>
        <div class="tag-item-info">
          <div class="tag-item-name">${t.assigned_name || t.hardware_id}</div>
          <div class="tag-item-meta">${t.current_section || '—'} · ${t.battery_level !== undefined ? Math.round(t.battery_level) + '%' : ''}</div>
        </div>
        ${t.alert_status !== 'NORMAL' ? `<span class="tag-item-badge ${badgeClass}">${t.alert_status.replace('_',' ')}</span>` : ''}
      </div>`;
  }).join('');
}

function alertDotClass(status, state) {
  if (state === 'OFFLINE') return 'dot-gray';
  if (status === 'NORMAL') return 'dot-green';
  if (status === 'RESTRICTED_ZONE' || status === 'CRITICAL_VITALS') return 'dot-red';
  return 'dot-yellow';
}

function alertBadgeClass(status) {
  if (status === 'RESTRICTED_ZONE' || status === 'CRITICAL_VITALS') return 'badge-red';
  return 'badge-yellow';
}

// ── Render Alert Feed ─────────────────────────────────────────────────────────
function renderAlertFeed() {
  const list = document.getElementById('alertList');
  const empty = document.getElementById('alertEmpty');
  document.getElementById('alertCountBadge').textContent = alerts.length;
  if (alerts.length === 0) {
    empty.style.display = 'flex';
    return;
  }
  empty.style.display = 'none';
  list.innerHTML = alerts.map(a => `
    <div class="alert-item" onclick="zoomToAlert(${a.id})">
      <div class="alert-item-header">
        <div class="alert-item-dot ${a.alert_type === 'RESTRICTED_ZONE' ? 'dot-red' : 'dot-yellow'}"></div>
        <span class="alert-item-type ${a.alert_type === 'RESTRICTED_ZONE' ? 'red' : 'yellow'}">${a.alert_type.replace('_',' ')}</span>
        <span class="alert-item-time">${timeAgo(a.triggered_at)}</span>
      </div>
      <div class="alert-item-body">${a.message || a.alert_type} — ${a.section_name || 'Unknown section'}</div>
      ${a.state === 'ACTIVE' ? `<button class="alert-ack-btn" onclick="event.stopPropagation();acknowledgeAlert(${a.id})">Acknowledge</button>` : ''}
    </div>`).join('');
}

// ── Acknowledge Alert ─────────────────────────────────────────────────────────
async function acknowledgeAlert(alertId) {
  const res = await API.post(`/alerts/${alertId}/acknowledge`);
  if (res && res.ok) { await loadAlerts(); }
}

// ── Select / Zoom to Tracker ──────────────────────────────────────────────────
function selectTracker(id) {
  selectedTrackerId = id;
  renderTagList();
  const t = trackers.find(x => x.id === id);
  if (!t) return;
  showTagCard(t);
  zoomToPosition(t.position);
}

function showTagCard(t) {
  const card = document.getElementById('tagCard');
  const dotEl = document.getElementById('tagCardDot');
  const dotClass = alertDotClass(t.alert_status, t.asset_state);
  dotEl.className = `tag-card-dot ${dotClass}`;
  document.getElementById('tagCardName').textContent = t.assigned_name || t.hardware_id;
  document.getElementById('tagCardType').textContent = t.category;
  document.getElementById('tagCardHardwareId').textContent = t.hardware_id;
  document.getElementById('tagCardSection').textContent = t.current_section || '—';
  document.getElementById('tagCardBattery').textContent = t.battery_level !== undefined ? Math.round(t.battery_level) + '%' : '—';
  document.getElementById('tagCardLastSeen').textContent = t.last_report_time ? timeAgo(new Date(t.last_report_time * 1000).toISOString()) : '—';
  if (t.heart_rate) {
    document.getElementById('tagCardHRRow').style.display = 'flex';
    document.getElementById('tagCardHR').textContent = Math.round(t.heart_rate) + ' bpm';
  } else { document.getElementById('tagCardHRRow').style.display = 'none'; }
  if (t.sp_o2) {
    document.getElementById('tagCardSpO2Row').style.display = 'flex';
    document.getElementById('tagCardSpO2').textContent = Math.round(t.sp_o2) + '%';
  } else { document.getElementById('tagCardSpO2Row').style.display = 'none'; }
  card.style.display = 'block';
}

function closeTagCard() {
  document.getElementById('tagCard').style.display = 'none';
  selectedTrackerId = null;
  renderTagList();
}

// ── Filters ────────────────────────────────────────────────────────────────────
function toggleFilter(type) {
  const checkbox = document.getElementById(`filter${type.charAt(0).toUpperCase() + type.slice(1)}`);
  filters[type] = checkbox.checked;
  renderTagList();
}

// ── Stats ──────────────────────────────────────────────────────────────────────
function updateStats() {
  document.getElementById('statActive').textContent = trackers.filter(t => t.asset_state === 'ACTIVE').length;
  document.getElementById('statAlerts').textContent = alerts.length;
  document.getElementById('statCheckedIn').textContent = trackers.filter(t => t.check_status === 'CHECKED_IN').length;
}

// ── View Toggle ────────────────────────────────────────────────────────────────
function setView(view) {
  currentView = view;
  document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
  document.querySelector(`.view-btn[data-view="${view}"]`).classList.add('active');
  document.getElementById('map2d').style.display = view === '2d' ? 'block' : 'none';
  document.getElementById('map3d').style.display = view === '3d' ? 'block' : 'none';
  if (view === '3d' && !map3d) initMap3D();
}

// ── Map helpers ──────────────────────────────────────────────────────────────
function zoomToPosition(pos) {
  if (currentView === '2d' && map2d) map2d.panTo([pos.y, pos.x]);
}
function zoomToAlert(alertId) {
  const a = alerts.find(x => x.id === alertId);
  if (a && a.tracker_id) selectTracker(a.tracker_id);
}

// ── SSE Stream ─────────────────────────────────────────────────────────────────
let evtSource = null;
function startSSE() {
  const token = localStorage.getItem('holo_access_token');
  evtSource = new EventSource(`/api/stream/positions?token=${encodeURIComponent(token)}`);
  evtSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.type === 'position_update') {
        handlePositionUpdate(data.tracker);
      } else if (data.type === 'alert_update') {
        loadAlerts();
      }
    } catch { /* ignore */ }
  };
  evtSource.onerror = () => {
    // Reconnect after 5s
    evtSource.close();
    setTimeout(startSSE, 5000);
  };
}

function handlePositionUpdate(trackerData) {
  const idx = trackers.findIndex(t => t.id === trackerData.id);
  if (idx >= 0) {
    trackers[idx] = { ...trackers[idx], ...trackerData };
  }
  if (selectedTrackerId === trackerData.id) {
    showTagCard(trackers[idx]);
  }
  renderTrackerDots();
}

// ── Notifications ──────────────────────────────────────────────────────────────
async function loadNotifications() {
  const res = await API.get('/notifications');
  const data = await API.json(res);
  if (!res || !res.ok) return;
  const list = document.getElementById('notifList');
  if (!data.items || data.items.length === 0) {
    list.innerHTML = '<div class="notif-empty">No new notifications</div>';
    return;
  }
  list.innerHTML = data.items.map(n => `
    <div class="notif-item ${n.is_read ? '' : 'unread'}" onclick="openNotification(${n.id})">
      <div class="notif-item-title">${n.title}</div>
      <div class="notif-item-body">${n.message || ''}</div>
      <div class="notif-item-time">${timeAgo(n.created_at)}</div>
    </div>`).join('');
}

function toggleNotifications() {
  const dropdown = document.getElementById('notifDropdown');
  const isOpen = dropdown.style.display !== 'none';
  dropdown.style.display = isOpen ? 'none' : 'block';
  if (!isOpen) loadNotifications();
}

document.addEventListener('click', e => {
  if (!e.target.closest('#notifBtn') && !e.target.closest('.notifications-dropdown')) {
    document.getElementById('notifDropdown').style.display = 'none';
  }
});

async function markAllRead() {
  await API.post('/notifications/read-all');
  loadNotifications();
}

// ── Search Modal ───────────────────────────────────────────────────────────────
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
    ...(ts || []).map(t => ({ type: 'tracker', name: t.assigned_name || t.hardware_id, meta: t.category, id: t.id })),
    ...(users || []).map(u => ({ type: 'user', name: u.display_name || u.username, meta: u.role, id: u.id })),
  ];
  if (all.length === 0) {
    document.getElementById('searchResults').innerHTML = '<div class="search-hint">No results found</div>';
    return;
  }
  document.getElementById('searchResults').innerHTML = all.map(item => `
    <div class="search-result-item" onclick="onSearchResultClick('${item.type}',${item.id})">
      <div class="search-result-icon">
        <i class="fa-solid ${item.type === 'tracker' ? 'fa-signal' : 'fa-user'}"></i>
      </div>
      <div class="search-result-info">
        <div class="search-result-name">${item.name}</div>
        <div class="search-result-meta">${item.meta} · ${item.type}</div>
      </div>
    </div>`).join('');
}
function onSearchResultClick(type, id) {
  closeSearch();
  if (type === 'tracker') selectTracker(id);
}

// ── Keyboard shortcuts ─────────────────────────────────────────────────────────
function setupKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
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

// ── Map tools ─────────────────────────────────────────────────────────────────
function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen();
  } else {
    document.exitFullscreen();
  }
}
function resetCamera() {
  if (currentView === '2d' && map2d) map2d.setView([0, 0], 16);
}
function toggleHeatmap() { /* Phase 4 */ }
function toggleLayers() { /* Phase 4 */ }
function viewHistory() { document.getElementById('historyBar').style.display = 'block'; }
function closeHistory() { document.getElementById('historyBar').style.display = 'none'; }
function triggerAlarm() { /* Phase 4 */ }
function editTag() { window.location.href = `/trackers?id=${selectedTrackerId}`; }

// ── Placeholder map renderers (implemented in visualization/) ──────────────────
function initMap2D() { /* loaded from map2d.js */ }
function initMap3D() { /* loaded from map3d.js */ }
function renderTrackerDots() { /* called from map2d/map3d */ }
