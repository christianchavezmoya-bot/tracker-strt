/**
 * RTLS commissioning UI — readiness checklist, WiFi setup card, MQTT status.
 */
'use strict';

let _readinessCache = null;

async function loadRtlsReadiness() {
  try {
    const res = await API.get('/system/rtls-readiness');
    const data = await API.json(res);
    if (res && res.ok) {
      _readinessCache = data;
      return data;
    }
  } catch (e) {
    console.warn('RTLS readiness load failed', e);
  }
  return null;
}

function readinessIcon(ok) {
  return ok
    ? '<i class="fa-solid fa-circle-check" style="color:var(--green)"></i>'
    : '<i class="fa-solid fa-circle-exclamation" style="color:var(--yellow)"></i>';
}

function renderReadinessPanel(containerId, opts = {}) {
  const el = document.getElementById(containerId);
  if (!el || !_readinessCache) return;
  const r = _readinessCache;
  const compact = opts.compact === true;
  const items = (r.checklist || []).map(item => `
    <div class="rtls-check-item" style="display:flex;gap:10px;align-items:flex-start;padding:${compact ? '6px 0' : '8px 0'};font-size:12px;line-height:1.45">
      <span style="flex-shrink:0;margin-top:2px">${readinessIcon(item.ok)}</span>
      <div>
        <div style="color:${item.ok ? 'var(--text-secondary)' : 'var(--text-primary)'};font-weight:${item.ok ? '500' : '600'}">${item.label}</div>
        ${item.hint && !item.ok ? `<div style="color:var(--text-muted);font-size:11px;margin-top:2px">${item.hint}</div>` : ''}
      </div>
    </div>`).join('');

  el.innerHTML = `
    <div class="rtls-readiness" style="background:rgba(255,255,255,0.03);border:1px solid var(--border);border-radius:10px;padding:${compact ? '10px 12px' : '14px'};margin-bottom:12px">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:${compact ? '6px' : '10px'}">
        <div style="font-size:11px;font-weight:700;letter-spacing:0.08em;color:var(--text-muted)">SETUP PROGRESS</div>
        <div style="font-size:12px;font-weight:700;color:${r.ready ? 'var(--green)' : 'var(--cyan)'}">${r.progress_pct || 0}%</div>
      </div>
      ${items}
      ${!r.ready ? `
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
          <a href="/?mode=setup" class="btn btn-primary btn-sm" style="text-decoration:none;font-size:11px;padding:6px 10px"><i class="fa-solid fa-map-pin"></i> Place anchors</a>
          <a href="/nodes" class="btn btn-secondary btn-sm" style="text-decoration:none;font-size:11px;padding:6px 10px"><i class="fa-solid fa-wifi"></i> View nodes</a>
        </div>` : `<div style="margin-top:8px;font-size:11px;color:var(--green)"><i class="fa-solid fa-check"></i> Ready — tags should appear on the map</div>`}
    </div>`;
}

function renderMapEmptyBanner() {
  const el = document.getElementById('rtlsMapBanner');
  if (!el || !_readinessCache) return;
  const r = _readinessCache;
  if (r.ready || r.tags_visible) {
    el.style.display = 'none';
    return;
  }
  const need = r.anchors_needed || 0;
  let msg = 'Complete setup to see tags on the map.';
  if (!_readinessCache.broker?.running) {
    msg = 'Turn on “Receive data from WiFi nodes” in Settings → Network & MQTT.';
  } else if (need > 0) {
    msg = `Place ${need} more anchor${need === 1 ? '' : 's'} on the map (need ${r.anchors_required} total).`;
  } else if ((r.nodes_total || 0) === 0) {
    msg = 'No WiFi nodes detected yet — check unit MQTT settings or open the setup card on Anchors page.';
  }
  el.innerHTML = `<i class="fa-solid fa-circle-info"></i><span>${msg}</span>
    <a href="/settings" style="color:#5eead4;margin-left:6px">Settings</a>
    <button type="button" onclick="this.parentElement.style.display='none'" aria-label="Dismiss" style="background:none;border:none;color:#5eead4;cursor:pointer;margin-left:auto"><i class="fa-solid fa-xmark"></i></button>`;
  el.style.display = 'flex';
}

async function refreshRtlsSetupUi() {
  await loadRtlsReadiness();
  renderReadinessPanel('rtlsReadinessPanel');
  renderReadinessPanel('rtlsReadinessPanelCompact', { compact: true });
  renderMapEmptyBanner();
  updateMqttStatusChip();
}

function updateMqttStatusChip() {
  const chip = document.getElementById('mqttStatusChip');
  if (!chip || !_readinessCache?.broker) return;
  const b = _readinessCache.broker;
  const running = b.running;
  const enabled = b.enabled;
  chip.style.display = 'inline-flex';
  chip.title = running ? `Receiving node data on port ${b.port}` : (enabled ? 'MQTT receiver enabled but not running' : 'MQTT receiver off');
  chip.innerHTML = running
    ? '<span class="mqtt-chip-dot" style="background:var(--green)"></span> Node data ON'
    : (enabled
      ? '<span class="mqtt-chip-dot" style="background:var(--yellow)"></span> MQTT issue'
      : '<span class="mqtt-chip-dot" style="background:var(--text-muted)"></span> Node data OFF');
  chip.className = 'mqtt-status-chip ' + (running ? 'chip-ok' : (enabled ? 'chip-warn' : 'chip-off'));
}

async function loadWifiSetupCard(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  try {
    const res = await API.get('/system/wifi-unit-setup');
    const data = await API.json(res);
    if (!res || !res.ok) return;
    const rows = [
      ['Broker address', data.broker_host],
      ['Port', String(data.broker_port)],
      ['Topic', data.topic],
      ['Payload format', data.payload_format],
      ['Example', data.example_payload],
    ];
    el.innerHTML = `
      <div style="font-size:13px;font-weight:600;margin-bottom:10px;color:var(--text-primary)"><i class="fa-solid fa-copy" style="color:var(--cyan)"></i> ${data.title || 'WiFi unit settings'}</div>
      <div style="font-size:12px;color:var(--text-muted);margin-bottom:12px">${data.note || ''}</div>
      <table style="width:100%;font-size:12px;border-collapse:collapse">
        ${rows.map(([k, v]) => `<tr><td style="padding:6px 8px 6px 0;color:var(--text-muted);white-space:nowrap">${k}</td><td class="mono" style="padding:6px 0;color:var(--cyan);word-break:break-all">${v}</td></tr>`).join('')}
      </table>
      <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
        <button type="button" class="btn btn-secondary btn-sm" onclick="copyWifiSetup()"><i class="fa-solid fa-clipboard"></i> Copy all</button>
        <button type="button" class="btn btn-ghost btn-sm" onclick="copyWifiSetupField('broker')"><i class="fa-solid fa-server"></i> Copy address</button>
      </div>`;
    window._wifiSetupCard = data;
  } catch (e) {
    el.innerHTML = '<div style="color:var(--text-muted);font-size:12px">Could not load setup card</div>';
  }
}

function copyWifiSetup() {
  const d = window._wifiSetupCard;
  if (!d) return;
  const text = [
    `Broker: ${d.broker_host}`,
    `Port: ${d.broker_port}`,
    `Topic: ${d.topic}`,
    `Format: ${d.payload_format}`,
    `Example: ${d.example_payload}`,
  ].join('\n');
  navigator.clipboard?.writeText(text).then(() => showToast?.('Copied WiFi unit settings', 'success'));
}

function copyWifiSetupField(which) {
  const d = window._wifiSetupCard;
  if (!d) return;
  const val = which === 'broker' ? d.broker_host : d.broker_url;
  navigator.clipboard?.writeText(val).then(() => showToast?.('Copied', 'success'));
}

async function loadMqttNetworkPanel() {
  const statusEl = document.getElementById('mqttNetworkStatus');
  const toggleEl = document.getElementById('mqttBrokerToggle');
  if (!statusEl) return;
  statusEl.innerHTML = '<div class="table-loading"><i class="fa-solid fa-circle-notch fa-spin"></i> Loading…</div>';
  try {
    const res = await API.get('/system/mqtt-broker');
    const data = await API.json(res);
    if (!res || !res.ok) throw new Error('load failed');
    if (toggleEl) toggleEl.checked = !!data.enabled;
    const running = data.running;
    const pill = running ? 'pill-green' : (data.enabled ? 'pill-yellow' : 'pill-gray');
    const label = running ? 'Running' : (data.enabled ? 'Not running' : 'Off');
    statusEl.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px">
        <div class="hw-summary-card" style="padding:14px;text-align:center">
          <div class="status-pill ${pill}" style="margin:0 auto 8px"><span class="status-dot-sm"></span>${label}</div>
          <div style="font-size:11px;color:var(--text-muted)">Status</div>
        </div>
        <div class="hw-summary-card" style="padding:14px;text-align:center">
          <div style="font-size:18px;font-weight:700;font-family:var(--font-mono);color:var(--cyan)">${data.port}</div>
          <div style="font-size:11px;color:var(--text-muted)">Port</div>
        </div>
        <div class="hw-summary-card" style="padding:14px;text-align:center">
          <div style="font-size:18px;font-weight:700;font-family:var(--font-mono);color:var(--cyan)">${data.message_count || 0}</div>
          <div style="font-size:11px;color:var(--text-muted)">Messages received</div>
        </div>
      </div>
      <div style="font-size:12px;color:var(--text-secondary);line-height:1.6;margin-bottom:8px">
        <strong>Address for WiFi units:</strong> <span class="mono" style="color:var(--cyan)">${data.broker_url || ''}</span>
      </div>
      ${data.last_error ? `<div style="font-size:12px;color:var(--red);margin-top:8px">${data.last_error}</div>` : ''}
      <div id="wifiSetupCardSettings" style="margin-top:16px"></div>`;
    await loadWifiSetupCard('wifiSetupCardSettings');
  } catch (e) {
    statusEl.innerHTML = '<div style="color:var(--red);font-size:13px">Failed to load MQTT status</div>';
  }
}

async function onMqttBrokerToggleChange(checked) {
  try {
    const res = await API.post('/system/mqtt-broker', { enabled: !!checked });
    const data = await API.json(res);
    if (res && res.ok) {
      showToast?.(checked ? 'Now receiving data from WiFi nodes' : 'WiFi node receiver turned off', checked ? 'success' : 'info');
      await loadMqttNetworkPanel();
      await refreshRtlsSetupUi();
    } else {
      showToast?.('Failed: ' + (data?.error || res?.statusText), 'error');
      const t = document.getElementById('mqttBrokerToggle');
      if (t) t.checked = !checked;
    }
  } catch (e) {
    showToast?.('Network error', 'error');
  }
}

window.loadRtlsReadiness = loadRtlsReadiness;
window.renderReadinessPanel = renderReadinessPanel;
window.refreshRtlsSetupUi = refreshRtlsSetupUi;
window.loadWifiSetupCard = loadWifiSetupCard;
window.loadMqttNetworkPanel = loadMqttNetworkPanel;
window.onMqttBrokerToggleChange = onMqttBrokerToggleChange;
window.copyWifiSetup = copyWifiSetup;
