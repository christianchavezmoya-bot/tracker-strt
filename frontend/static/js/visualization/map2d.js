/**
 * HOLO-RTLS — 2D Floor Plan Map (Leaflet + CRS.Simple)
 *
 * Workflow:
 *  1. Load calibration from /api/positioning/calibration
 *  2. If calibrated: use pixel→real transform → load floor plan image
 *  3. If not calibrated: show upload/calibrate button
 *  4. Render zones (circles + section polygons)
 *  5. Render tag dots (live from trackers dict, updated via SSE)
 *  6. Click-to-calibrate: user clicks 3+ points → POST to /api/positioning/calibration
 */
window._map2d = null;
let _floorPlanLayer = null;
let _zoneLayers = [];
let _sectionLayers = [];
let _calibrationPoints = [];   // {pixel_x, pixel_y, real_x, real_y}
let _isCalibrated = false;
let _imageWidth = 1000;
let _imageHeight = 3000;  // Will be set from loaded image
let _originX = 0, _originY = 0;  // Real-world origin offset
let _scaleX = 1, _scaleY = 1;    // Pixels per real-world meter

// ── Init ──────────────────────────────────────────────────────────────────────
function initMap2D() {
  const container = document.getElementById('map2d');

  window._map2d = L.map('map2d', {
    center: [0, 0],
    zoom: 14,
    zoomControl: false,
    crs: L.CRS.Simple,
    minZoom: 8,
    maxZoom: 22,
    attributionControl: false,
  });

  // Zoom controls
  L.control.zoom({ position: 'bottomright' }).addTo(window._map2d);

  // Load calibration + render
  loadCalibration().then(() => {
    loadFloorPlanImage();
    renderZones();
  });

  // Scale bar
  L.control.scale({ imperial: false, position: 'bottomleft', maxWidth: 200 }).addTo(window._map2d);

  // Click to add calibration point
  window._map2d.on('click', onMapClick);

  // Render tracker dots (triggers after trackers are loaded)
  window.renderTrackerDots = renderTrackerDots;
  window.updateTrackerDot = updateTrackerDot;
  window.zoomToPosition = zoomToPosition;
}

// ── Calibration ───────────────────────────────────────────────────────────────
async function loadCalibration() {
  try {
    const res = await API.get('/positioning/calibration');
    const data = await API.json(res);
    if (!res || !res.ok) return;

    const status = data.status || {};
    const sectionId = 0;  // Default section
    const cal = status[sectionId] || {};

    if (cal.calibrated) {
      _isCalibrated = true;
      _calibrationPoints = cal.calibration_points || [];
      showCalibrationStatus(true);
    } else {
      _isCalibrated = false;
      showCalibrationStatus(false);
    }
  } catch (e) {
    console.warn('Could not load calibration:', e);
  }
}

function showCalibrationStatus(calibrated) {
  // Add a status overlay to the map
  const existing = document.getElementById('mapCalibrationStatus');
  if (existing) existing.remove();

  const el = document.createElement('div');
  el.id = 'mapCalibrationStatus';
  el.style.cssText = `
    position: absolute; top: 10px; left: 50%; transform: translateX(-50%);
    z-index: 1000; padding: 8px 16px; border-radius: 20px;
    font-size: 12px; font-family: var(--font-mono); font-weight: 600;
    backdrop-filter: blur(8px); cursor: pointer;
  `;

  if (calibrated) {
    el.style.cssText += 'background: rgba(105,255,71,0.15); border: 1px solid rgba(105,255,71,0.4); color: var(--green);';
    el.innerHTML = '<i class="fa-solid fa-check-circle"></i> Map calibrated';
    el.onclick = enterCalibrationMode;
  } else {
    el.style.cssText += 'background: rgba(255,68,68,0.15); border: 1px solid rgba(255,68,68,0.4); color: var(--red);';
    el.innerHTML = '<i class="fa-solid fa-map-pin"></i> Click to calibrate map';
    el.onclick = enterCalibrationMode;
  }
  document.getElementById('map2d').style.position = 'relative';
  document.getElementById('map2d').appendChild(el);
}

function enterCalibrationMode() {
  _calibrationPoints = [];
  showCalibrationStatus(false);

  const info = document.createElement('div');
  info.id = 'calibrationInfo';
  info.style.cssText = `
    position: absolute; top: 60px; left: 50%; transform: translateX(-50%);
    z-index: 1000; background: var(--bg-card); border: 1px solid var(--border-bright);
    border-radius: var(--radius); padding: 14px 18px; max-width: 320px; text-align: center;
    font-size: 13px; color: var(--text-primary); box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  `;
  info.innerHTML = `
    <div style="font-weight:700;color:var(--cyan);margin-bottom:8px">Calibration Mode</div>
    <div style="color:var(--text-muted);font-size:12px;margin-bottom:10px">
      Click 3 or more known points on the map.<br>
      For each point, enter its real-world coordinates (meters).
    </div>
    <div style="margin-bottom:10px" id="calibrationCount">Points: 0/3</div>
    <button class="btn btn-secondary" onclick="exitCalibrationMode()" style="font-size:12px;padding:5px 14px">Cancel</button>
  `;
  document.getElementById('map2d').appendChild(info);
}

function exitCalibrationMode() {
  document.getElementById('calibrationInfo')?.remove();
  _calibrationPoints = [];
  loadCalibration();
}

async function onMapClick(e) {
  // Check if in calibration mode
  const infoEl = document.getElementById('calibrationInfo');
  if (!infoEl) return;

  const px = e.containerPoint.x;
  const py = e.containerPoint.y;

  const realX = prompt('Real-world X (meters):', '0');
  if (realX === null) return;
  const realY = prompt('Real-world Y (meters):', '0');
  if (realY === null) return;

  _calibrationPoints.push({
    pixel_x: parseFloat(px),
    pixel_y: parseFloat(py),
    real_x: parseFloat(realX),
    real_y: parseFloat(realY),
  });

  document.getElementById('calibrationCount').textContent =
    `Points: ${_calibrationPoints.length}/3 (need at least 3)`;

  // Add marker on map
  L.circleMarker([e.latlng.lat, e.latlng.lng], {
    radius: 8, color: 'var(--cyan)', fillColor: 'var(--cyan)',
    fillOpacity: 0.8, weight: 2,
  }).addTo(window._map2d).bindTooltip(`${_calibrationPoints.length}: (${realX}, ${realY})`);

  if (_calibrationPoints.length >= 3) {
    await saveCalibration();
  }
}

async function saveCalibration() {
  if (_calibrationPoints.length < 3) return;
  try {
    for (const pt of _calibrationPoints) {
      await API.post('/positioning/calibration', {
        pixel_x: pt.pixel_x,
        pixel_y: pt.pixel_y,
        real_x: pt.real_x,
        real_y: pt.real_y,
        section_id: 0,
      });
    }
    document.getElementById('calibrationInfo')?.remove();
    await loadCalibration();
    loadFloorPlanImage();
  } catch (e) {
    alert('Failed to save calibration: ' + e);
  }
}

// ── Floor plan image ─────────────────────────────────────────────────────────
async function loadFloorPlanImage() {
  // Remove existing floor plan
  if (_floorPlanLayer) {
    window._map2d.removeLayer(_floorPlanLayer);
    _floorPlanLayer = null;
  }

  // Try to load from sections (map_sections table)
  try {
    const res = await API.get('/zones/sections');
    const data = await API.json(res);
    if (res && res.ok && data.items && data.items.length > 0) {
      const section = data.items[0];
      if (section.image_url) {
        loadFloorPlanFromURL(section.image_url, section);
        return;
      }
    }
  } catch {}

  // Fallback: try default location
  loadFloorPlanFromURL('/static/assets/floor-plan-placeholder.png', null);
}

function loadFloorPlanFromURL(url, section) {
  const img = new Image();
  img.onload = () => {
    _imageWidth = img.naturalWidth || 1000;
    _imageHeight = img.naturalHeight || 1000;

    // Compute bounds based on calibration or default
    let southWest, northEast;
    if (_isCalibrated && _calibrationPoints.length >= 2) {
      // Use calibration to set real-world bounds
      const minX = Math.min(..._calibrationPoints.map(p => p.real_x));
      const maxX = Math.max(..._calibrationPoints.map(p => p.real_x));
      const minY = Math.min(..._calibrationPoints.map(p => p.real_y));
      const maxY = Math.max(..._calibrationPoints.map(p => p.real_y));
      // Map to pixel coords
      southWest = [_imageHeight - maxY, minX];
      northEast = [_imageHeight - minY, maxX];
    } else {
      // Default: pixel = real-world (1:1, 1000x1000m)
      southWest = [_imageHeight, 0];
      northEast = [0, _imageWidth];
    }

    _floorPlanLayer = L.imageOverlay(url, [southWest, northEast], {
      opacity: 0.92,
      crossOrigin: true,
    }).addTo(window._map2d);

    // Draw calibration grid overlay
    drawGridOverlay();
  };
  img.onerror = () => {
    // No image — draw a placeholder grid
    drawGridOverlay();
  };
  img.src = url;
}

function drawGridOverlay() {
  // Draw a subtle grid on the map
  const bounds = window._map2d.getBounds();
  const step = 50;  // 50m grid

  for (let x = 0; x <= (_imageWidth || 1000); x += step) {
    const latlng1 = L.CRS.Simple.unproject(L.point(x, 0));
    const latlng2 = L.CRS.Simple.unproject(L.point(x, _imageHeight || 1000));
    L.polyline([latlng1, latlng2], {
      color: 'rgba(0,229,255,0.08)', weight: 1,
    }).addTo(window._map2d);
  }
  for (let y = 0; y <= (_imageHeight || 1000); y += step) {
    const latlng1 = L.CRS.Simple.unproject(L.point(0, y));
    const latlng2 = L.CRS.Simple.unproject(L.point(_imageWidth || 1000, y));
    L.polyline([latlng1, latlng2], {
      color: 'rgba(0,229,255,0.08)', weight: 1,
    }).addTo(window._map2d);
  }
}

// ── Zones ────────────────────────────────────────────────────────────────────
async function renderZones() {
  // Clear existing zone layers
  _zoneLayers.forEach(l => window._map2d.removeLayer(l));
  _sectionLayers.forEach(l => window._map2d.removeLayer(l));
  _zoneLayers = [];
  _sectionLayers = [];

  try {
    // Load zones
    const zRes = await API.get('/zones');
    const zData = await API.json(zRes);
    if (zRes && zRes.ok && zData.items) {
      zData.items.forEach(zone => {
        // to_dict() returns { position: {x, y, z}, ... }
        const pos = zone.position || { x: zone.pos_x || 0, y: zone.pos_y || 0 };
        const latlng = L.CRS.Simple.unproject(L.point(pos.x, pos.y));

        const colorMap = {
          RESTRICTED: { color: '#ff4444', fill: '#ff4444' },
          DANGER: { color: '#ff6b35', fill: '#ff6b35' },
          CHECK_IN: { color: '#00e5ff', fill: '#00e5ff' },
          CHECK_OUT: { color: '#00e5ff', fill: '#00e5ff' },
          NORMAL: { color: '#00e5ff', fill: '#00e5ff' },
        };
        const ztype = zone.zone_type;  // string name from to_dict()
        const c = colorMap[ztype] || colorMap.NORMAL;

        const layer = L.circle(latlng, {
          radius: zone.radius || 5,
          color: c.color,
          fillColor: c.fill,
          fillOpacity: 0.06,
          weight: ztype === 'RESTRICTED' ? 2 : 1,
          opacity: ztype === 'RESTRICTED' ? 0.7 : 0.3,
          dashArray: ztype === 'DANGER' ? '6,4' : null,
        }).addTo(window._map2d);

        layer.bindTooltip(zone.name, {
          permanent: false, direction: 'top',
          className: 'holo-tooltip',
        });
        _zoneLayers.push(layer);
      });
    }

    // Load sections (polygons)
    const sRes = await API.get('/zones/sections');
    const sData = await API.json(sRes);
    if (sRes && sRes.ok && sData.items) {
      sData.items.forEach(section => {
        // to_dict() returns parsed 'polygon' array
        const coords = section.polygon;
        if (!coords || !Array.isArray(coords) || coords.length < 3) return;

        // coords may be flat [[x,y], ...] or ring-structured
        const ring = Array.isArray(coords[0]) ?
          (Array.isArray(coords[0][0]) ? coords[0] : coords) : coords;

        const latlngs = ring.map(([x, y]) =>
          L.CRS.Simple.unproject(L.point(
            typeof x === 'number' ? x : parseFloat(x),
            typeof y === 'number' ? y : parseFloat(y)
          ))
        );

        const layer = L.polygon(latlngs, {
          color: section.color_hex || '#00e5ff',
          fillColor: section.color_hex || '#00e5ff',
          fillOpacity: section.is_restricted ? 0.08 : 0.03,
          weight: 1.5,
          opacity: 0.35,
        }).addTo(window._map2d);

        layer.bindTooltip(section.name, { sticky: true, className: 'holo-tooltip' });
        _sectionLayers.push(layer);
      });
    }
  } catch (e) {
    console.warn('Could not load zones:', e);
  }
}

// ── Tracker dots ─────────────────────────────────────────────────────────────
function renderTrackerDots() {
  if (!window._map2d) return;

  // Remove existing dots
  window._map2d.eachLayer(layer => {
    if (layer._isTrackerDot) window._map2d.removeLayer(layer);
  });

  Object.values(window.trackers || {}).forEach(t => {
    if (t.pos_x === undefined || t.pos_y === undefined) return;
    addTrackerDot(t);
  });
}

function addTrackerDot(t) {
  const latlng = L.CRS.Simple.unproject(L.point(t.pos_x, t.pos_y));
  const dotClass = dotClassForTracker(t);
  const isSelected = window.selectedTrackerId === t.id;

  const icon = L.divIcon({
    className: '',
    html: `<div class="tracker-dot ${dotClass} ${isSelected ? 'selected' : ''}"
                 id="dot-${t.id}" style="position:relative"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });

  const marker = L.marker(latlng, { icon, zIndexOffset: isSelected ? 1000 : 0 });
  marker._isTrackerDot = true;
  marker.addTo(window._map2d);

  marker.on('click', () => {
    window.selectTracker(t.id);
  });

  const name = t.assigned_name || t.hardware_id || '—';
  const section = t.current_section || t.section_name || '—';
  const speed = t.speed !== null ? `· ${t.speed.toFixed(1)}m/s` : '';
  const batt = t.battery_level !== undefined ? `· ${Math.round(t.battery_level)}%` : '';
  marker.bindTooltip(
    `<b>${name}</b><br>${section} ${speed}${batt}`,
    { direction: 'top', offset: [0, -8], className: 'holo-tooltip' }
  );
}

function updateTrackerDot(tid, pos) {
  if (!window._map2d) return;
  const tracker = window.trackers && window.trackers[tid];
  if (!tracker) return;

  // Find existing marker by dot element id
  let existing = null;
  window._map2d.eachLayer(layer => {
    if (layer._isTrackerDot &&
        layer._icon && layer._icon.querySelector &&
        layer._icon.querySelector(`#dot-${tid}`)) {
      existing = layer;
    }
  });

  const latlng = L.CRS.Simple.unproject(L.point(pos.x, pos.y));

  if (existing) {
    existing.setLatLng(latlng);
  } else {
    // Add new dot for previously unseen tracker
    addTrackerDot({ ...tracker, pos_x: pos.x, pos_y: pos.y, pos_z: pos.z });
  }
}

function dotClassForTracker(t) {
  if (t.asset_state === 'OFFLINE') return 'dot-gray';
  if (t.alert_status === 'RESTRICTED_ZONE' || t.alert_status === 'CRITICAL_VITALS') return 'dot-red';
  if (t.alert_status !== 'NORMAL') return 'dot-yellow';
  return 'dot-green';
}

function zoomToPosition(x, y) {
  if (!window._map2d) return;
  const latlng = L.CRS.Simple.unproject(L.point(x, y));
  window._map2d.setView(latlng, Math.max(window._map2d.getZoom(), 17), { animate: true });
}
