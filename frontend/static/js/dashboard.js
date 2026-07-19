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

// ── Historical Playback ─────────────────────────────────────────────────────
let isPlayback = false;
let playbackInterval = null;
let playbackSpeed = 1;
let playbackStart = null;  // datetime of playback window start
let playbackEnd = null;    // datetime of playback window end
let playbackCursor = null;  // current playback position (Date)
let playbackData = {};     // tracker_id → [{x, y, z, timestamp}]
let playbackIsPlaying = false;
let heatmapVisible = false;
let heatmapCanvas = null;
let heatmapCtx = null;
let zoneOccupancyOpen = false;
let zoneOccupancyTimer = null;

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  if (!API.isLoggedIn()) {
    window.location.href = '/login';
    return;
  }
  await loadUserInfo();
  await Promise.all([loadTrackers(), loadAlerts(), loadNodes(), loadZones()]);
  updateStats();
  updateDashboardKPIs();
  initHeatmapCanvas();
  renderZoneOccupancy();
  zoneOccupancyTimer = setInterval(() => {
    if (!isPlayback) renderZoneOccupancy();
  }, 10000);
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
  if (!heatmapCanvas) initHeatmapCanvas();
  heatmapVisible = !heatmapVisible;
  if (heatmapVisible) {
    heatmapCanvas.style.display = 'block';
    renderHeatmapFrame();
  } else {
    heatmapCanvas.style.display = 'none';
    if (heatmapCtx) {
      heatmapCtx.clearRect(0, 0, heatmapCanvas.width, heatmapCanvas.height);
    }
  }
}

function initHeatmapCanvas() {
  heatmapCanvas = document.getElementById('heatmapCanvas');
  if (!heatmapCanvas) return;
  heatmapCtx = heatmapCanvas.getContext('2d');
  // Size canvas to parent
  const container = heatmapCanvas.parentElement;
  const ro = new ResizeObserver(() => {
    heatmapCanvas.width = container.offsetWidth;
    heatmapCanvas.height = container.offsetHeight;
    if (heatmapVisible) renderHeatmapFrame();
  });
  ro.observe(container);
}

function renderHeatmapFrame() {
  if (!heatmapCtx || !heatmapVisible) return;
  const canvas = heatmapCanvas;
  const ctx = heatmapCtx;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const map2d = window._map2d;
  const bounds = map2d ? map2d.getBounds() : null;
  const zoom = map2d ? map2d.getZoom() : 16;

  Object.values(trackers).forEach(t => {
    if (t.pos_x === undefined || t.pos_y === undefined) return;
    let px, py;
    if (bounds) {
      // Convert world coords to screen pixels using Leaflet latLng
      const latlng = map2d.unproject([t.pos_x, t.pos_y], zoom);
      px = map2d.latLngToContainerPoint(latlng).x;
      py = map2d.latLngToContainerPoint(latlng).y;
    } else {
      // Fallback: scale world coords to canvas size
      px = ((t.pos_x % 1000) / 1000) * canvas.width;
      py = ((t.pos_y % 1000) / 1000) * canvas.height;
    }

    const radius = 80;
    const grad = ctx.createRadialGradient(px, py, 0, px, py, radius);
    grad.addColorStop(0, 'rgba(0, 229, 255, 0.7)');
    grad.addColorStop(0.4, 'rgba(0, 229, 255, 0.25)');
    grad.addColorStop(1, 'rgba(0, 229, 255, 0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(px, py, radius, 0, Math.PI * 2);
    ctx.fill();
  });
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
  // Ignore SSE updates during playback — playback uses history data only
  if (isPlayback) return;

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

// ── Phase 10: Full Historical Playback ───────────────────────────────────────
async function startPlayback() {
  if (isPlayback) return;
  isPlayback = true;
  playbackIsPlaying = false;
  playbackSpeed = 1;
  playbackData = {};

  // Window: last 1 hour
  playbackEnd = new Date();
  playbackStart = new Date(playbackEnd.getTime() - 60 * 60 * 1000);
  playbackCursor = new Date(playbackEnd.getTime() - 60 * 60 * 1000);

  // Show playback bar
  document.getElementById('playbackBar').style.display = 'flex';
  document.getElementById('playbackBadgeLive').style.display = 'none';
  document.getElementById('playbackBadgePlayback').style.display = 'inline-block';
  document.getElementById('playbackPlayIcon').className = 'fa-solid fa-play';
  document.getElementById('playbackPlayBtn').classList.remove('playing');
  updatePlaybackSpeedUI(1);

  // Update range labels
  document.getElementById('playbackRangeStart').textContent = fmtTime(playbackStart);

  // Fetch history for all trackers in parallel
  const trackerIds = Object.keys(trackers);
  await Promise.all(trackerIds.map(async tid => {
    try {
      const res = await API.get(`/positioning/history/${tid}?limit=2000`);
      const data = await API.json(res);
      if (data && data.history) {
        // Filter to window
        playbackData[tid] = data.history
          .filter(p => {
            const ts = new Date(p.timestamp);
            return ts >= playbackStart && ts <= playbackEnd;
          })
          .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
      }
    } catch (e) {
      playbackData[tid] = [];
    }
  }));

  // Configure slider
  const slider = document.getElementById('playbackSlider');
  slider.min = 0;
  slider.max = 3600; // 1 hour in seconds
  slider.value = 0;

  renderPlaybackFrame();
  startPlaybackInterval();
}

function stopPlayback() {
  if (!isPlayback) return;
  isPlayback = false;
  playbackIsPlaying = false;
  if (playbackInterval) {
    clearInterval(playbackInterval);
    playbackInterval = null;
  }
  document.getElementById('playbackBar').style.display = 'none';
  // Restore live badge
  document.getElementById('playbackBadgeLive').style.display = 'inline-block';
  document.getElementById('playbackBadgePlayback').style.display = 'none';
  // Clear playback cursor
  playbackCursor = null;
  playbackData = {};
  // Force re-render from live data
  if (window.renderTrackerDots) window.renderTrackerDots();
  renderTagList();
  updateStats();
}

function startPlaybackInterval() {
  if (playbackInterval) clearInterval(playbackInterval);
  playbackInterval = setInterval(advancePlayback, 1000); // tick every second
}

function advancePlayback() {
  if (!isPlayback || !playbackIsPlaying) return;
  const msToAdd = playbackSpeed * 1000;
  playbackCursor = new Date(playbackCursor.getTime() + msToAdd);
  if (playbackCursor >= playbackEnd) {
    playbackCursor = new Date(playbackEnd);
    playbackIsPlaying = false;
    if (playbackInterval) {
      clearInterval(playbackInterval);
      playbackInterval = null;
    }
    document.getElementById('playbackPlayIcon').className = 'fa-solid fa-play';
    document.getElementById('playbackPlayBtn').classList.remove('playing');
  }
  renderPlaybackFrame();
  // Sync slider
  const elapsed = Math.floor((playbackCursor.getTime() - playbackStart.getTime()) / 1000);
  document.getElementById('playbackSlider').value = Math.min(elapsed, 3600);
}

function renderPlaybackFrame() {
  if (!playbackCursor) return;
  // Update timestamp display
  document.getElementById('playbackTimestamp').textContent = fmtDateTime(playbackCursor);

  // For each tracker, find the most recent history point <= cursor
  Object.keys(playbackData).forEach(tid => {
    const points = playbackData[tid];
    if (!points || points.length === 0) return;
    let frame = null;
    for (let i = points.length - 1; i >= 0; i--) {
      if (new Date(points[i].timestamp) <= playbackCursor) {
        frame = points[i];
        break;
      }
    }
    if (!frame) return;
    // Update tracker object
    if (trackers[tid]) {
      trackers[tid].pos_x = frame.x;
      trackers[tid].pos_y = frame.y;
      trackers[tid].pos_z = frame.z || 0;
      trackers[tid].last_seen = frame.timestamp;
    }
    // Update map
    if (window.updateTrackerDot) window.updateTrackerDot(tid, frame);
    if (window.updateTrackerDot3D) window.updateTrackerDot3D(tid, frame);
    // Update tag card if selected
    if (selectedTrackerId === tid) {
      showTagCard(trackers[tid]);
    }
  });

  // Update tag list time display
  const row = selectedTrackerId
    ? document.querySelector(`.tag-item[data-id="${selectedTrackerId}"]`)
    : null;
  if (row) {
    const timeEl = row.querySelector('.tag-item-time');
    if (timeEl) timeEl.textContent = timeAgo(playbackCursor.toISOString());
  }
}

function seekPlayback(timestamp) {
  if (!isPlayback) return;
  playbackCursor = new Date(timestamp);
  if (playbackCursor < playbackStart) playbackCursor = new Date(playbackStart);
  if (playbackCursor > playbackEnd) playbackCursor = new Date(playbackEnd);
  renderPlaybackFrame();
}

function stepPlayback(deltaSeconds) {
  if (!isPlayback) return;
  playbackIsPlaying = false;
  if (playbackInterval) {
    clearInterval(playbackInterval);
    playbackInterval = null;
  }
  document.getElementById('playbackPlayIcon').className = 'fa-solid fa-play';
  document.getElementById('playbackPlayBtn').classList.remove('playing');
  playbackCursor = new Date(playbackCursor.getTime() + deltaSeconds * 1000);
  if (playbackCursor < playbackStart) playbackCursor = new Date(playbackStart);
  if (playbackCursor > playbackEnd) playbackCursor = new Date(playbackEnd);
  // Sync slider
  const elapsed = Math.floor((playbackCursor.getTime() - playbackStart.getTime()) / 1000);
  document.getElementById('playbackSlider').value = Math.min(Math.max(elapsed, 0), 3600);
  renderPlaybackFrame();
}

function setPlaybackSpeed(speed) {
  if (!isPlayback) return;
  playbackSpeed = speed;
  updatePlaybackSpeedUI(speed);
  // Restart interval with new speed
  startPlaybackInterval();
}

function updatePlaybackSpeedUI(speed) {
  document.querySelectorAll('.speed-btn').forEach(btn => {
    btn.classList.toggle('active', parseInt(btn.dataset.speed) === speed);
  });
}

function togglePlaybackPlay() {
  if (!isPlayback) return;
  playbackIsPlaying = !playbackIsPlaying;
  const icon = document.getElementById('playbackPlayIcon');
  const btn = document.getElementById('playbackPlayBtn');
  if (playbackIsPlaying) {
    icon.className = 'fa-solid fa-pause';
    btn.classList.add('playing');
    startPlaybackInterval();
  } else {
    icon.className = 'fa-solid fa-play';
    btn.classList.remove('playing');
    if (playbackInterval) {
      clearInterval(playbackInterval);
      playbackInterval = null;
    }
  }
}

function onPlaybackSliderInput(value) {
  if (!isPlayback) return;
  playbackIsPlaying = false;
  if (playbackInterval) {
    clearInterval(playbackInterval);
    playbackInterval = null;
  }
  document.getElementById('playbackPlayIcon').className = 'fa-solid fa-play';
  document.getElementById('playbackPlayBtn').classList.remove('playing');
  playbackCursor = new Date(playbackStart.getTime() + parseInt(value) * 1000);
  renderPlaybackFrame();
}

// ── Dashboard KPIs ───────────────────────────────────────────────────────────
async function updateDashboardKPIs() {
  const kpiTrackers = document.getElementById('kpiTrackers');
  const kpiAlerts = document.getElementById('kpiAlerts');
  const kpiOffline = document.getElementById('kpiOffline');
  const kpiAvgResponse = document.getElementById('kpiAvgResponse');
  const kpiSystemDot = document.getElementById('kpiSystemDot');
  const kpiSystemStatus = document.getElementById('kpiSystemStatus');

  // Active trackers count
  const activeCount = trackerList.filter(t => t.asset_state === 'ACTIVE').length;
  if (kpiTrackers) kpiTrackers.textContent = activeCount;

  // Alerts count
  const alertCount = alerts.filter(a => a.state === 'ACTIVE').length;
  if (kpiAlerts) kpiAlerts.textContent = alertCount;

  // Offline count
  const offlineCount = trackerList.filter(t => t.asset_state === 'OFFLINE' || t.asset_state === 'DECOMMISSIONED').length;
  if (kpiOffline) kpiOffline.textContent = offlineCount;

  // System status
  try {
    const [statusRes, countsRes] = await Promise.all([
      API.get('/settings/status'),
      API.get('/alerts/counts'),
    ]);
    const statusData = await API.json(statusRes);
    const countsData = await API.json(countsRes);

    // Bridge status
    const bridgeUp = statusData && statusData.bridge_online === true;
    if (kpiSystemDot) {
      kpiSystemDot.className = `kpi-dot ${bridgeUp ? 'dot-green' : 'dot-red'}`;
    }
    if (kpiSystemStatus) {
      kpiSystemStatus.textContent = bridgeUp ? 'ONLINE' : 'OFFLINE';
      kpiSystemStatus.style.color = bridgeUp ? 'var(--green)' : 'var(--red)';
    }

    // Average response from counts
    if (countsData && countsData.avg_response_minutes !== undefined) {
      if (kpiAvgResponse) kpiAvgResponse.textContent = countsData.avg_response_minutes.toFixed(1) + 'm';
    }
  } catch (e) {
    // Fallback: use computed values
    if (kpiSystemDot) kpiSystemDot.className = 'kpi-dot dot-gray';
    if (kpiSystemStatus) { kpiSystemStatus.textContent = '—'; kpiSystemStatus.style.color = ''; }
  }
}

// ── Zone Occupancy ───────────────────────────────────────────────────────────
function toggleZoneOccupancy() {
  const section = document.getElementById('zoneOccupancySection');
  zoneOccupancyOpen = !zoneOccupancyOpen;
  section.classList.toggle('open', zoneOccupancyOpen);
  if (zoneOccupancyOpen && !isPlayback) renderZoneOccupancy();
}

async function renderZoneOccupancy() {
  const body = document.getElementById('zoneOccBody');
  const loading = document.getElementById('zoneOccLoading');
  if (!body) return;

  // Show loading
  if (loading) loading.style.display = 'block';

  try {
    const res = await API.get('/positioning/live');
    const data = await API.json(res);
    if (!data || !data.positions) {
      body.innerHTML = '<div class="zone-occ-loading">No data</div>';
      return;
    }

    // Count trackers per section
    const sectionCounts = {};
    data.positions.forEach(p => {
      const section = p.section_name || p.section || 'Unknown';
      if (!sectionCounts[section]) sectionCounts[section] = 0;
      sectionCounts[section]++;
    });

    const entries = Object.entries(sectionCounts).sort((a, b) => b[1] - a[1]);
    const maxCount = entries.length > 0 ? entries[0][1] : 1;

    if (entries.length === 0) {
      body.innerHTML = '<div class="zone-occ-loading">No zone data</div>';
      return;
    }

    body.innerHTML = entries.map(([section, count]) => {
      const pct = maxCount > 0 ? Math.round((count / maxCount) * 100) : 0;
      return `
      <div class="zone-bar-wrap">
        <div class="zone-bar-label" title="${section}">${section}</div>
        <div class="zone-bar-track">
          <div class="zone-bar" style="width:${pct}%"></div>
        </div>
        <div class="zone-bar-count">${count}</div>
      </div>`;
    }).join('');
  } catch (e) {
    body.innerHTML = '<div class="zone-occ-loading">Failed to load</div>';
  }
}

// ── Helpers ─────────────────────────────────────────────────────────────────
function fmtTime(d) {
  if (!d) return '—';
  const date = d instanceof Date ? d : new Date(d);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function fmtDateTime(d) {
  if (!d) return '—';
  const date = d instanceof Date ? d : new Date(d);
  return date.toLocaleString([], {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
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
