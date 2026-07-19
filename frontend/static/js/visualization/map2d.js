/**
 * HOLO-RTLS — 2D Floor Plan Map (Leaflet + CRS.Simple)
 *
 * Workflow:
 *  1. Load calibration from /api/positioning/calibration
 *  2. If calibrated: apply affine transform → place nodes by click
 *  3. If not calibrated: 2-point calibration wizard → compute affine transform
 *  4. After calibration: click anywhere = auto real-world coords
 *  5. Node placement: select pre-registered node from dropdown → assign name → save position
 */
window._map2d = null;
let _floorPlanLayer = null;
let _zoneLayers = [];
let _sectionLayers = [];
let _gridLines = [];
let _nodeMarkers = [];

// ── Calibration state ─────────────────────────────────────────────────────────
let _isCalibrated = false;
let _calibrationPoints = [];
let _imageWidth = 1000;
let _imageHeight = 3000;

// ── Affine transform: real_x = a*x + b*y + c / real_y = d*x + e*y + f ──────
let _tx_a = 1, _tx_b = 0, _tx_c = 0;
let _ty_d = 0, _ty_e = 1, _ty_f = 0;

// ── Node placement state ──────────────────────────────────────────────────────
let _isNodePlacementMode = false;
let _placementGhost = null;
let _unplacedNodes = [];   // nodes fetched from API, not yet on map
let _mapMode = 'normal';

// ── Init ──────────────────────────────────────────────────────────────────────
function initMap2D() {
  window._map2d = L.map('map2d', {
    center: [0, 0], zoom: 14, zoomControl: false,
    crs: L.CRS.Simple, minZoom: 8, maxZoom: 22, attributionControl: false,
  });

  L.control.zoom({ position: 'bottomright' }).addTo(window._map2d);
  L.control.scale({ imperial: false, position: 'bottomleft', maxWidth: 200 }).addTo(window._map2d);

  loadCalibration().then(() => {
    loadFloorPlanImage();
    renderZones();
    renderNodeMarkers();
  });

  window._map2d.on('click', onMapClick);
  window._map2d.on('mousemove', onMapMouseMove);

  // Expose for dashboard.js / other callers
  window.renderTrackerDots = renderTrackerDots;
  window.updateTrackerDot = updateTrackerDot;
  window.zoomToPosition = zoomToPosition;
  window.renderZones = renderZones;
  window.toggleZoneLayer = toggleZoneLayer;
  window.toggleSectionLayer = toggleSectionLayer;
  window.toggleGridLayer = toggleGridLayer;
  window.enterCalibrationMode = enterCalibrationMode;
  window.enterNodePlacementMode = enterNodePlacementMode;
  window.exitPlacementMode = exitPlacementMode;
  window.renderNodeMarkers = renderNodeMarkers;
  window.refreshUnplacedNodes = loadUnplacedNodes;
}

// ══════════════════════════════════════════════════════════════════════════════
//  COORDINATE TRANSFORMS
// ══════════════════════════════════════════════════════════════════════════════

function pixelToReal(px, py) {
  return { x: _tx_a * px + _tx_b * py + _tx_c, y: _ty_d * px + _ty_e * py + _ty_f };
}

function computeAffineTransform(points) {
  if (points.length < 2) return;
  if (points.length === 2) {
    const { pixel_x: x1, pixel_y: y1, real_x: X1, real_y: Y1 } = points[0];
    const { pixel_x: x2, pixel_y: y2, real_x: X2, real_y: Y2 } = points[1];
    _tx_a = (X2 - X1) / (x2 - x1); _tx_b = 0; _tx_c = X1 - _tx_a * x1;
    _ty_d = 0; _ty_e = (Y2 - Y1) / (y2 - y1); _ty_f = Y1 - _ty_e * y1;
  } else {
    let sum_xx = 0, sum_xy = 0, sum_x = 0, sum_yy = 0, sum_y = 0, sum_n = 0;
    let sum_XX = 0, sum_XY = 0, sum_YX = 0, sum_YY = 0;
    points.forEach(p => {
      sum_xx += p.pixel_x * p.pixel_x; sum_xy += p.pixel_x * p.pixel_y; sum_x += p.pixel_x;
      sum_yy += p.pixel_y * p.pixel_y; sum_y += p.pixel_y; sum_n++;
      sum_XX += p.real_x * p.pixel_x; sum_XY += p.real_x * p.pixel_y;
      sum_YX += p.real_y * p.pixel_x; sum_YY += p.real_y * p.pixel_y;
    });
    const det = sum_xx * sum_yy - sum_xy * sum_xy;
    if (Math.abs(det) < 1e-10) return;
    _tx_a = (sum_XX * sum_yy - sum_XY * sum_xy) / det;
    _tx_b = (sum_XY * sum_xx - sum_XX * sum_xy) / det;
    _tx_c = (sum_x * sum_XY - sum_XX * sum_y) / det;
    _ty_d = (sum_YX * sum_yy - sum_YY * sum_xy) / det;
    _ty_e = (sum_YY * sum_xx - sum_YX * sum_xy) / det;
    _ty_f = (sum_y * sum_YY - sum_YX * sum_y) / det;
  }
  console.info('[Calibration] Transform:', { tx: [_tx_a, _tx_b, _tx_c], ty: [_ty_d, _ty_e, _ty_f] });
}

// ══════════════════════════════════════════════════════════════════════════════
//  CALIBRATION
// ══════════════════════════════════════════════════════════════════════════════

async function loadCalibration() {
  try {
    const res = await API.get('/positioning/calibration');
    const data = await API.json(res);
    if (!res || !res.ok) return;
    const cal = (data.status && (data.status['0'] || data.status[0])) || {};
    if (cal.calibrated && cal.calibration_points && cal.calibration_points.length >= 2) {
      _isCalibrated = true;
      _calibrationPoints = cal.calibration_points;
      computeAffineTransform(_calibrationPoints);
      showCalibrationBadge(true);
    } else {
      _isCalibrated = false;
      showCalibrationBadge(false);
    }
  } catch (e) {
    console.warn('Could not load calibration:', e);
    _isCalibrated = false;
    showCalibrationBadge(false);
  }
}

function showCalibrationBadge(calibrated) {
  const existing = document.getElementById('mapCalibrationBadge');
  if (existing) existing.remove();
  const el = document.createElement('div');
  el.id = 'mapCalibrationBadge';
  Object.assign(el.style, {
    position: 'absolute', top: '10px', left: '50%', transform: 'translateX(-50%)',
    zIndex: '1000', padding: '6px 14px', borderRadius: '20px',
    fontSize: '12px', fontFamily: 'var(--font-mono, monospace)',
    fontWeight: '600', cursor: 'pointer', pointerEvents: 'auto',
    backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', gap: '6px',
  });
  if (calibrated) {
    Object.assign(el.style, { background: 'rgba(0,229,255,0.12)', border: '1px solid rgba(0,229,255,0.4)', color: 'var(--cyan, #00e5ff)' });
    el.innerHTML = '<i class="fa-solid fa-check-circle"></i> Map calibrated — click to recalibrate';
  } else {
    Object.assign(el.style, { background: 'rgba(255,165,0,0.12)', border: '1px solid rgba(255,165,0,0.4)', color: '#ffa500' });
    el.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Calibrate map — click to start';
  }
  el.onclick = enterCalibrationMode;
  const mapEl = document.getElementById('map2d');
  if (mapEl) { mapEl.style.position = 'relative'; mapEl.appendChild(el); }
}

function enterCalibrationMode() {
  if (_isNodePlacementMode) exitPlacementMode();
  _mapMode = 'calibrate';
  _calibrationPoints = [];
  document.getElementById('calibrationForm')?.remove();
  document.getElementById('coordReadout')?.remove();
  showCalibrationBadge(false);
  const mapEl = document.getElementById('map2d');
  if (!mapEl) return;
  mapEl.style.position = 'relative';

  const panel = document.createElement('div');
  panel.id = 'calibrationForm';
  Object.assign(panel.style, {
    position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
    zIndex: '1001', background: 'rgba(8,15,30,0.97)',
    border: '1px solid rgba(0,229,255,0.25)', borderRadius: '14px', padding: '20px 24px',
    width: '360px', maxWidth: '90vw', boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
    backdropFilter: 'blur(12px)', fontFamily: 'var(--font-body, system-ui)',
  });
  panel.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
      <div style="font-size:14px;font-weight:700;color:var(--cyan,#00e5ff)">
        <i class="fa-solid fa-wand-magic-sparkles"></i> Map Calibration
      </div>
      <button id="calCloseBtn" style="background:none;border:none;color:var(--text-muted,#888);cursor:pointer;font-size:14px">
        <i class="fa-solid fa-xmark"></i>
      </button>
    </div>
    <p style="font-size:12px;color:var(--text-muted,#aaa);margin:0 0 14px;line-height:1.6">
      Click <strong style="color:#fff">2 reference points</strong> on the map image.
      For each, enter the real-world coordinates shown on your floor plan.
    </p>
    <div id="calStep1">
      <div style="font-size:11px;font-weight:700;color:var(--text-muted,#888);margin-bottom:8px;letter-spacing:0.06em">POINT 1</div>
      <div id="cal1Info" style="font-size:11px;color:var(--cyan,#00e5ff);margin-bottom:8px">
        <i class="fa-solid fa-hand-pointer"></i> Click a reference point on the map…
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
        <div>
          <label style="font-size:10px;color:var(--text-muted,#888);display:block;margin-bottom:4px">X (meters)</label>
          <input id="calX1" type="number" step="0.1" placeholder="e.g. -142.5"
            style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);
            border-radius:6px;padding:7px 10px;color:#fff;font-size:13px;outline:none;box-sizing:border-box">
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-muted,#888);display:block;margin-bottom:4px">Y (meters)</label>
          <input id="calY1" type="number" step="0.1" placeholder="e.g. 87.3"
            style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);
            border-radius:6px;padding:7px 10px;color:#fff;font-size:13px;outline:none;box-sizing:border-box">
        </div>
      </div>
      <button id="calSave1Btn" disabled style="width:100%;padding:8px;
        background:rgba(0,229,255,0.1);border:1px solid rgba(0,229,255,0.3);
        border-radius:6px;color:#666;font-size:12px;cursor:not-allowed;font-weight:600">
        Save Point 1
      </button>
    </div>
    <div id="calStep2" style="display:none;margin-top:16px">
      <div style="font-size:11px;font-weight:700;color:var(--text-muted,#888);margin-bottom:8px;letter-spacing:0.06em">POINT 2</div>
      <div id="cal2Info" style="font-size:11px;color:var(--cyan,#00e5ff);margin-bottom:8px">
        <i class="fa-solid fa-hand-pointer"></i> Click second reference point…
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
        <div>
          <label style="font-size:10px;color:var(--text-muted,#888);display:block;margin-bottom:4px">X (meters)</label>
          <input id="calX2" type="number" step="0.1" placeholder="e.g. 156.2"
            style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);
            border-radius:6px;padding:7px 10px;color:#fff;font-size:13px;outline:none;box-sizing:border-box">
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-muted,#888);display:block;margin-bottom:4px">Y (meters)</label>
          <input id="calY2" type="number" step="0.1" placeholder="e.g. 203.8"
            style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);
            border-radius:6px;padding:7px 10px;color:#fff;font-size:13px;outline:none;box-sizing:border-box">
        </div>
      </div>
      <button id="calSave2Btn" disabled style="width:100%;padding:8px;
        background:rgba(0,229,255,0.1);border:1px solid rgba(0,229,255,0.3);
        border-radius:6px;color:#666;font-size:12px;cursor:not-allowed;font-weight:600">
        Save Point 2 &amp; Apply
      </button>
    </div>
    <div id="calDone" style="display:none;text-align:center;padding:16px 0">
      <div style="font-size:24px;margin-bottom:8px">&#127881;</div>
      <div style="font-size:14px;font-weight:700;color:#6bff47;margin-bottom:4px">Calibration Complete!</div>
      <div style="font-size:12px;color:var(--text-muted,#aaa)">
        Coordinates will be calculated automatically. Go to Hardware Setup to register nodes first.
      </div>
    </div>
  `;
  mapEl.appendChild(panel);

  panel.querySelector('#calCloseBtn').onclick = exitCalibrationMode;

  const enableBtn = (xId, yId, btnId) => {
    const btn = document.getElementById(btnId);
    const enable = () => {
      const x = document.getElementById(xId).value.trim();
      const y = document.getElementById(yId).value.trim();
      const ok = !!(x && y);
      btn.disabled = !ok;
      btn.style.background = ok ? 'rgba(0,229,255,0.15)' : 'rgba(0,229,255,0.1)';
      btn.style.color = ok ? 'var(--cyan,#00e5ff)' : '#666';
      btn.style.cursor = ok ? 'pointer' : 'not-allowed';
    };
    document.getElementById(xId).addEventListener('input', enable);
    document.getElementById(yId).addEventListener('input', enable);
    return btn;
  };

  const btn1 = enableBtn('calX1', 'calY1', 'calSave1Btn');
  btn1.onclick = () => {
    _calibrationPoints[0] = {
      _px: _calibrationPoints[0]?._px, _py: _calibrationPoints[0]?._py,
      real_x: parseFloat(document.getElementById('calX1').value),
      real_y: parseFloat(document.getElementById('calY1').value),
    };
    document.getElementById('cal1Info').innerHTML = '<i class="fa-solid fa-check" style="color:#6bff47"></i> Point 1 saved';
    document.getElementById('calStep1').style.opacity = '0.5';
    document.getElementById('calStep2').style.display = 'block';
    document.getElementById('cal2Info').innerHTML = '<i class="fa-solid fa-hand-pointer" style="color:#ffa500"></i> Click second point on map, then enter coords…';
    const btn2 = enableBtn('calX2', 'calY2', 'calSave2Btn');
    btn2.onclick = async () => {
      _calibrationPoints[1] = {
        _px: _calibrationPoints[1]?._px, _py: _calibrationPoints[1]?._py,
        real_x: parseFloat(document.getElementById('calX2').value),
        real_y: parseFloat(document.getElementById('calY2').value),
      };
      const p1 = _calibrationPoints[0], p2 = _calibrationPoints[1];
      if (!p1._px || !p2._px) { showToast('Click both points on the map before saving.', 'error'); return; }
      p1.pixel_x = p1._px; p1.pixel_y = p1._py;
      p2.pixel_x = p2._px; p2.pixel_y = p2._py;
      computeAffineTransform(_calibrationPoints);
      await saveCalibration();
      document.getElementById('calStep2').style.display = 'none';
      document.getElementById('calDone').style.display = 'block';
    };
  };
}

function exitCalibrationMode() {
  _mapMode = 'normal';
  document.getElementById('calibrationForm')?.remove();
  document.getElementById('coordReadout')?.remove();
  showCalibrationBadge(_isCalibrated);
}

async function saveCalibration() {
  try {
    await API.post('/positioning/calibration', {
      calibration_points: _calibrationPoints.map(p => ({
        pixel_x: p.pixel_x, pixel_y: p.pixel_y, real_x: p.real_x, real_y: p.real_y,
      })),
      calibrated: true, section_id: 0,
    });
    _isCalibrated = true;
    showCalibrationBadge(true);
    showCoordReadout();
  } catch (e) {
    console.error('Failed to save calibration:', e);
  }
}

// ══════════════════════════════════════════════════════════════════════════════
//  UNPLACED NODES (fetched once, refreshed on demand)
// ══════════════════════════════════════════════════════════════════════════════

async function loadUnplacedNodes() {
  try {
    const res = await API.get('/nodes');
    const data = await API.json(res);
    if (!res || !res.ok) return [];
    _unplacedNodes = (data.items || []).filter(n => n.pos_x == null && n.pos_y == null);
  } catch {
    _unplacedNodes = [];
  }
}

// ══════════════════════════════════════════════════════════════════════════════
//  NODE PLACEMENT MODE
// ══════════════════════════════════════════════════════════════════════════════

async function enterNodePlacementMode() {
  if (!_isCalibrated) {
    showToast('Please calibrate the map first (2 reference points).', 'error');
    enterCalibrationMode();
    return;
  }
  if (_mapMode === 'calibrate') exitCalibrationMode();
  _mapMode = 'place_node';
  _isNodePlacementMode = true;

  document.getElementById('nodePlacementForm')?.remove();
  document.getElementById('coordReadout')?.remove();
  document.getElementById('nodePlacementBanner')?.remove();

  await loadUnplacedNodes();

  if (_unplacedNodes.length === 0) {
    showToast('No unplaced nodes found.\n\nGo to Hardware Setup → Anchors / Nodes → Add Node to register a node first.', 'error');
    _isNodePlacementMode = false;
    _mapMode = 'normal';
    return;
  }

  const banner = document.createElement('div');
  banner.id = 'nodePlacementBanner';
  Object.assign(banner.style, {
    position: 'absolute', top: '10px', left: '50%', transform: 'translateX(-50%)',
    zIndex: '1001', padding: '7px 16px', borderRadius: '20px',
    background: 'rgba(0,229,255,0.12)', border: '1px solid rgba(0,229,255,0.4)',
    color: 'var(--cyan,#00e5ff)', fontSize: '12px', fontWeight: '600',
    backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', gap: '8px', whiteSpace: 'nowrap',
  });
  banner.innerHTML = `
    <i class="fa-solid fa-microchip"></i> Click on map to place a node
    <span style="opacity:0.5">·</span>
    <span id="coordPreview" style="font-family:monospace">—</span>
    <span style="opacity:0.5;margin-left:4px">·</span>
    <i class="fa-solid fa-xmark" style="opacity:0.6;cursor:pointer" onclick="window.exitPlacementMode()"></i>
  `;
  const mapEl = document.getElementById('map2d');
  if (mapEl) { mapEl.style.position = 'relative'; mapEl.appendChild(banner); }
  showCoordReadout();
}

function exitPlacementMode() {
  _mapMode = 'normal';
  _isNodePlacementMode = false;
  document.getElementById('nodePlacementForm')?.remove();
  document.getElementById('nodePlacementBanner')?.remove();
  document.getElementById('coordReadout')?.remove();
  _placementGhost?.remove();
  _placementGhost = null;
}

function showCoordReadout() {
  const existing = document.getElementById('coordReadout');
  if (existing) existing.remove();
  const el = document.createElement('div');
  el.id = 'coordReadout';
  Object.assign(el.style, {
    position: 'absolute', bottom: '12px', left: '12px', zIndex: '1000',
    background: 'rgba(8,15,30,0.9)', border: '1px solid rgba(0,229,255,0.2)',
    borderRadius: '8px', padding: '6px 12px',
    fontFamily: 'monospace', fontSize: '12px', color: 'var(--cyan,#00e5ff)',
    backdropFilter: 'blur(6px)', display: 'flex', gap: '12px',
  });
  el.innerHTML = `
    <span>X: <strong id="readoutX">—</strong></span>
    <span>Y: <strong id="readoutY">—</strong></span>
    <span style="opacity:0.4">m</span>
  `;
  const mapEl = document.getElementById('map2d');
  if (mapEl) mapEl.appendChild(el);
}

// ══════════════════════════════════════════════════════════════════════════════
//  NODE PLACEMENT FORM (shown on map click)
// ══════════════════════════════════════════════════════════════════════════════

function showNodeForm(realX, realY, pixelX, pixelY) {
  document.getElementById('nodePlacementForm')?.remove();
  _placementGhost?.remove();
  const mapEl = document.getElementById('map2d');
  if (!mapEl) return;
  mapEl.style.position = 'relative';

  const latlng = L.CRS.Simple.unproject(L.point(pixelX, pixelY));
  _placementGhost = L.circleMarker(latlng, { radius: 10, color: '#00e5ff', fillColor: '#00e5ff', fillOpacity: 0.5, weight: 2 }).addTo(window._map2d);

  const nodeOptions = _unplacedNodes.map(n =>
    `<option value="${n.id}" data-name="${n.assigned_name || n.mac_address || ''}" data-type="${n.node_type || ''}">
      ${n.assigned_name || n.mac_address || 'Node ' + n.id}
    </option>`
  ).join('');

  const panel = document.createElement('div');
  panel.id = 'nodePlacementForm';
  Object.assign(panel.style, {
    position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
    zIndex: '1002', background: 'rgba(8,15,30,0.97)',
    border: '1px solid rgba(0,229,255,0.3)', borderRadius: '14px', padding: '20px 24px',
    width: '360px', maxWidth: '90vw', boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
    backdropFilter: 'blur(12px)', fontFamily: 'var(--font-body, system-ui)',
  });

  panel.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
      <div style="font-size:14px;font-weight:700;color:var(--cyan,#00e5ff)">
        <i class="fa-solid fa-microchip"></i> Place Node
      </div>
      <button id="nodeFormClose" style="background:none;border:none;color:var(--text-muted,#888);cursor:pointer;font-size:14px">
        <i class="fa-solid fa-xmark"></i>
      </button>
    </div>

    <div style="font-size:12px;color:var(--text-muted,#aaa);margin-bottom:14px;padding:8px 10px;
      background:rgba(0,229,255,0.06);border-radius:6px;line-height:1.8">
      <div><i class="fa-solid fa-location-dot" style="color:var(--cyan,#00e5ff);margin-right:6px"></i>
        <strong>X:</strong> ${realX.toFixed(2)} m
        <span style="margin-left:10px"><strong>Y:</strong> ${realY.toFixed(2)} m</span>
      </div>
      <div style="font-size:10px;opacity:0.5">Auto-calculated from calibration</div>
    </div>

    <div style="margin-bottom:14px">
      <label style="font-size:11px;font-weight:700;color:var(--text-muted,#888);display:block;margin-bottom:6px;letter-spacing:0.05em">
        SELECT NODE *
      </label>
      <select id="nodeSelectInput"
        style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);
          border-radius:6px;padding:9px 12px;color:#fff;font-size:13px;outline:none;box-sizing:border-box;margin-bottom:10px">
        <option value="">— Choose a registered node —</option>
        ${nodeOptions}
      </select>
      <label style="font-size:11px;font-weight:700;color:var(--text-muted,#888);display:block;margin-bottom:6px;letter-spacing:0.05em">
        NODE NAME
      </label>
      <input id="nodeNameInput" type="text" placeholder="e.g. ANCHOR-A1 or edit existing name"
        style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);
          border-radius:6px;padding:9px 12px;color:#fff;font-size:14px;outline:none;box-sizing:border-box">
    </div>

    <div style="margin-bottom:14px">
        <label style="font-size:10px;color:var(--text-muted,#888);display:block;margin-bottom:4px">Floor (Z)</label>
        <input id="nodeZInput" type="number" value="0" step="1"
          style="width:120px;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);
            border-radius:6px;padding:7px 10px;color:#fff;font-size:13px;outline:none;box-sizing:border-box">
      </div>

    <div style="display:flex;gap:8px">
      <button id="nodeSaveBtn"
        style="flex:1;padding:9px;background:var(--cyan,#00e5ff);border:none;
          border-radius:8px;color:#081f3e;font-weight:700;font-size:13px;cursor:pointer">
        <i class="fa-solid fa-floppy-disk"></i> Save Position
      </button>
      <button id="nodeCancelBtn"
        style="padding:9px 14px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);
          border-radius:8px;color:var(--text-muted,#888);font-size:13px;cursor:pointer">
        Cancel
      </button>
    </div>
  `;
  mapEl.appendChild(panel);

  // Auto-fill name when a node is selected
  const nodeSelect = panel.querySelector('#nodeSelectInput');
  const nameInput = panel.querySelector('#nodeNameInput');
  nodeSelect.addEventListener('change', () => {
    const opt = nodeSelect.options[nodeSelect.selectedIndex];
    if (opt && opt.value) {
      nameInput.value = opt.dataset.name || '';
      nameInput.placeholder = 'Name updated above — change if needed';
    }
  });

  panel.querySelector('#nodeFormClose').onclick = closeNodeForm;
  panel.querySelector('#nodeCancelBtn').onclick = closeNodeForm;

  panel.querySelector('#nodeSaveBtn').onclick = async () => {
    const nodeId = parseInt(nodeSelect.value);
    if (!nodeId) { nodeSelect.focus(); return; }

    const name = (nameInput.value || nameInput.placeholder.replace('Name updated above — change if needed', '')).trim();
    const z = parseFloat(document.getElementById('nodeZInput').value) || 0;
        const btn = panel.querySelector('#nodeSaveBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Saving…';

    try {
      const res = await API.patch(`/nodes/${nodeId}`, {
        pos_x: realX, pos_y: realY, pos_z: z,
        assigned_name: name || undefined,
      });
      if (res && res.ok) {
        closeNodeForm();
        await renderNodeMarkers();
        if (window.showToast) {
          window.showToast(`"${name}" placed at X=${realX.toFixed(1)}, Y=${realY.toFixed(1)}`, 'success');
        }
        // Refresh unplaced nodes list
        await loadUnplacedNodes();
        // If no more unplaced nodes, exit placement mode
        if (_unplacedNodes.length === 0) {
          exitPlacementMode();
          if (window.showToast) {
            window.showToast('All nodes placed! Go to Hardware Setup for more.', 'success');
          }
        }
      } else {
        const err = await API.json(res);
        showToast('Failed: ' + (err?.error || res.statusText), 'error');
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Position';
      }
    } catch (e) {
      showToast('Error: ' + e.message, 'error');
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Position';
    }
  };

  nameInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') panel.querySelector('#nodeSaveBtn').click();
    if (e.key === 'Escape') closeNodeForm();
  });
}

function closeNodeForm() {
  document.getElementById('nodePlacementForm')?.remove();
  _placementGhost?.remove();
  _placementGhost = null;
}

// ══════════════════════════════════════════════════════════════════════════════
//  MAP EVENTS
// ══════════════════════════════════════════════════════════════════════════════

function onMapClick(e) {
  if (_sectionDrawMode || _mapMode === 'section_draw') {
    _addSectionVertex(e.latlng);
    return;
  }
  if (_zoneDrawMode || _mapMode === 'zone_draw') {
    _placeZoneAt(e.latlng);
    return;
  }
  const px = e.containerPoint.x;
  const py = e.containerPoint.y;
  if (_mapMode === 'calibrate') handleCalibrationClick(px, py);
  else if (_mapMode === 'place_node') handleNodePlacementClick(px, py);
}

function handleCalibrationClick(px, py) {
  if (!_calibrationPoints[0]?._px) {
    _calibrationPoints[0] = { _px: px, _py: py, real_x: 0, real_y: 0 };
    document.getElementById('cal1Info').innerHTML = `<i class="fa-solid fa-check" style="color:#6bff47"></i> Clicked (${Math.round(px)}, ${Math.round(py)}) — enter coords`;
    setTimeout(() => document.getElementById('calX1')?.focus(), 50);
  } else if (!_calibrationPoints[1]?._px) {
    _calibrationPoints[1] = { _px: px, _py: py, real_x: 0, real_y: 0 };
    document.getElementById('cal2Info').innerHTML = `<i class="fa-solid fa-check" style="color:#6bff47"></i> Clicked (${Math.round(px)}, ${Math.round(py)}) — enter coords`;
    setTimeout(() => document.getElementById('calX2')?.focus(), 50);
  } else {
    document.getElementById('cal2Info').innerHTML = '<i class="fa-solid fa-info-circle" style="color:#ffa500"></i> Save Point 2 first, then click to recalibrate';
  }
}

function handleNodePlacementClick(px, py) {
  if (!_isCalibrated) { enterCalibrationMode(); return; }
  const real = pixelToReal(px, py);
  const preview = document.getElementById('coordPreview');
  if (preview) preview.textContent = 'X=' + real.x.toFixed(1) + '  Y=' + real.y.toFixed(1);
  showNodeForm(real.x, real.y, px, py);
}

function onMapMouseMove(e) {
  const px = e.containerPoint.x, py = e.containerPoint.y;
  const rx = document.getElementById('readoutX');
  const ry = document.getElementById('readoutY');
  if (_isCalibrated) {
    const real = pixelToReal(px, py);
    if (rx) rx.textContent = real.x.toFixed(1);
    if (ry) ry.textContent = real.y.toFixed(1);
  } else {
    if (rx) rx.textContent = Math.round(px);
    if (ry) ry.textContent = Math.round(py);
  }
  if (_isNodePlacementMode) {
    const preview = document.getElementById('coordPreview');
    if (preview) {
      const real = _isCalibrated ? pixelToReal(px, py) : { x: Math.round(px), y: Math.round(py) };
      preview.textContent = 'X=' + real.x.toFixed(1) + '  Y=' + real.y.toFixed(1);
    }
  }
}

// ══════════════════════════════════════════════════════════════════════════════
//  NODE MARKERS
// ══════════════════════════════════════════════════════════════════════════════

async function renderNodeMarkers() {
  _nodeMarkers.forEach(m => window._map2d.removeLayer(m));
  _nodeMarkers = [];
  try {
    const res = await API.get('/nodes');
    const data = await API.json(res);
    if (!res || !res.ok || !data.items) return;
    data.items.forEach(node => {
      const px = node.pos_x ?? node.position?.x;
      const py = node.pos_y ?? node.position?.y;
      if (px == null || py == null) return;
      const latlng = L.CRS.Simple.unproject(L.point(px, py));
      const typeIconMap = { UWB_ANCHOR: 'fa-wifi', WIFI_AP: 'fa-wifi', GATEWAY: 'fa-tower-cell', REPEATER: 'fa-repeat' };
      const icon = typeIconMap[node.node_type] || 'fa-microchip';
      const label = node.assigned_name || node.mac_address || 'Node';
      const nodeIcon = L.divIcon({
        className: '', iconSize: [32, 32], iconAnchor: [16, 16],
        html: `<div class="node-marker">
          <div class="node-icon-wrap"><i class="fa-solid ${icon}"></i></div>
          <div class="node-label">${label}</div>
        </div>`,
      });
      const marker = L.marker(latlng, { icon: nodeIcon, zIndexOffset: 500, draggable: true });
      marker._isNodeMarker = true;
      marker._nodeId = node.id;
      marker._nodeData = node;
      marker.bindTooltip('<b>' + label + '</b><br>' + (node.node_type || '') + '<br>Drag to reposition', { direction: 'top', offset: [0, -18], className: 'holo-tooltip' });
      marker.on('click', () => {
        if (_isNodePlacementMode) { exitPlacementMode(); return; }
        showNodeDetail(node);
      });
      marker.on('dragend', async (e) => {
        const ll = e.target.getLatLng();
        const pt = L.CRS.Simple.project(ll);
        try {
          const res = await API.patch('/nodes/' + node.id, { pos_x: pt.x, pos_y: pt.y });
          if (res && res.ok) {
            if (window.showToast) window.showToast('Anchor moved', 'success');
            // Refresh coverage rings
            if (window.layerState && window.layerState.coverage) renderCoverageRings();
          } else if (window.showToast) window.showToast('Failed to save anchor position', 'error');
        } catch (err) {
          if (window.showToast) window.showToast('Network error saving anchor', 'error');
        }
      });
      marker.addTo(window._map2d);
      _nodeMarkers.push(marker);
    });
  } catch (e) { console.warn('Could not render node markers:', e); }
}

function showNodeDetail(node) {
  const px = node.pos_x ?? node.position?.x;
  const py = node.pos_y ?? node.position?.y;
  if (px == null || py == null) return;
  const latlng = L.CRS.Simple.unproject(L.point(px, py));
  const label = node.assigned_name || node.mac_address || 'Node';
  L.popup({ className: 'holo-popup' }).setLatLng(latlng).setContent(`
    <div style="font-family:var(--font-body,system-ui);min-width:180px">
      <div style="font-size:13px;font-weight:700;color:var(--cyan,#00e5ff);margin-bottom:6px">
        <i class="fa-solid fa-microchip"></i> ${label}
      </div>
      <div style="font-size:11px;color:#aaa;line-height:1.8">
        <div><strong>Type:</strong> ${node.node_type || '—'}</div>
        <div><strong>X:</strong> ${px?.toFixed(2) || '—'} m</div>
        <div><strong>Y:</strong> ${py?.toFixed(2) || '—'} m</div>
        <div><strong>Z:</strong> ${node.pos_z ?? node.position?.z ?? 0} (floor)</div>
        ${node.section_name ? '<div><strong>Section:</strong> ' + node.section_name + '</div>' : ''}
        <div><strong>MAC:</strong> <span style="font-family:monospace">${node.mac_address || '—'}</span></div>
        <div><strong>Status:</strong> <span style="color:${String(node.status||'').toUpperCase()!=='OFFLINE' ? '#6bff47' : '#ff4444'}">${node.status || (node.is_active !== false ? 'Active' : 'Offline')}</span></div>
        ${node.last_heartbeat ? `<div><strong>Heartbeat:</strong> ${node.last_heartbeat}</div>` : ''}
        <div><strong>Coverage:</strong> ${(_nodeCoverageScore(node) * 100).toFixed(0)}%</div>
      </div>
    </div>
  `).openOn(window._map2d);
}

// ══════════════════════════════════════════════════════════════════════════════
//  FLOOR PLAN IMAGE
// ══════════════════════════════════════════════════════════════════════════════

async function loadFloorPlanImage() {
  if (_floorPlanLayer) { window._map2d.removeLayer(_floorPlanLayer); _floorPlanLayer = null; }
  try {
    const res = await API.get('/zones/sections');
    const data = await API.json(res);
    if (res && res.ok && data.items && data.items.length > 0 && data.items[0].image_url) {
      loadFloorPlanFromURL(data.items[0].image_url);
      return;
    }
  } catch {}
  loadFloorPlanFromURL('/static/assets/floor-plan-placeholder.png');
}

function loadFloorPlanFromURL(url) {
  const img = new Image();
  img.onload = () => {
    _imageWidth = img.naturalWidth || 1000;
    _imageHeight = img.naturalHeight || 1000;
    let southWest, northEast;
    if (_isCalibrated && _calibrationPoints.length >= 2) {
      const allX = _calibrationPoints.map(p => p.real_x);
      const allY = _calibrationPoints.map(p => p.real_y);
      southWest = [_imageHeight - Math.max(...allY), Math.min(...allX)];
      northEast = [_imageHeight - Math.min(...allY), Math.max(...allX)];
    } else {
      southWest = [_imageHeight, 0]; northEast = [0, _imageWidth];
    }
    _floorPlanLayer = L.imageOverlay(url, [southWest, northEast], { opacity: 0.92, crossOrigin: true }).addTo(window._map2d);
    drawGridOverlay();
    renderNodeMarkers();
  };
  img.onerror = () => drawGridOverlay();
  img.src = url;
}

// ══════════════════════════════════════════════════════════════════════════════
//  ZONES & GRID
// ══════════════════════════════════════════════════════════════════════════════

function drawGridOverlay() {
  _gridLines.forEach(l => window._map2d.removeLayer(l));
  _gridLines = [];
  const step = 50;
  for (let x = 0; x <= (_imageWidth || 1000); x += step) {
    const l1 = L.polyline([L.CRS.Simple.unproject(L.point(x, 0)), L.CRS.Simple.unproject(L.point(x, _imageHeight || 1000))], { color: 'rgba(0,229,255,0.08)', weight: 1 }).addTo(window._map2d);
    _gridLines.push(l1);
  }
  for (let y = 0; y <= (_imageHeight || 1000); y += step) {
    const l2 = L.polyline([L.CRS.Simple.unproject(L.point(0, y)), L.CRS.Simple.unproject(L.point(_imageWidth || 1000, y))], { color: 'rgba(0,229,255,0.08)', weight: 1 }).addTo(window._map2d);
    _gridLines.push(l2);
  }
}

async function renderZones() {
  _zoneLayers.forEach(l => window._map2d.removeLayer(l));
  _sectionLayers.forEach(l => window._map2d.removeLayer(l));
  _zoneLayers = []; _sectionLayers = [];
  try {
    const zRes = await API.get('/zones');
    const zData = await API.json(zRes);
    if (zRes && zRes.ok && zData.items) {
      zData.items.forEach(zone => {
        const pos = zone.position || { x: zone.pos_x || 0, y: zone.pos_y || 0 };
        const latlng = L.CRS.Simple.unproject(L.point(pos.x, pos.y));
        const c = { RESTRICTED: { color: '#ff4444', fill: '#ff4444' }, DANGER: { color: '#ff6b35', fill: '#ff6b35' } }[zone.zone_type] || { color: '#00e5ff', fill: '#00e5ff' };
        const layer = L.circle(latlng, { radius: zone.radius || 5, color: c.color, fillColor: c.fill, fillOpacity: 0.06, weight: zone.zone_type === 'RESTRICTED' ? 2 : 1, opacity: zone.zone_type === 'RESTRICTED' ? 0.7 : 0.3, dashArray: zone.zone_type === 'DANGER' ? '6,4' : null }).addTo(window._map2d);
        layer.bindTooltip(zone.name + ' · click to edit', { permanent: false, direction: 'top', className: 'holo-tooltip' });
        layer._zoneData = zone;
        layer.on('click', (e) => {
          if (_zoneDrawMode || _sectionDrawMode) return;
          L.DomEvent.stopPropagation(e);
          _editZoneOnMap(zone);
        });
        _zoneLayers.push(layer);
      });
    }
    const sRes = await API.get('/zones/sections');
    const sData = await API.json(sRes);
    if (sRes && sRes.ok && sData.items) {
      sData.items.forEach(section => {
        const coords = section.polygon;
        if (!coords || !Array.isArray(coords) || coords.length < 3) return;
        const ring = Array.isArray(coords[0]) ? (Array.isArray(coords[0][0]) ? coords[0] : coords) : coords;
        const latlngs = ring.map(([x, y]) => L.CRS.Simple.unproject(L.point(typeof x === 'number' ? x : parseFloat(x), typeof y === 'number' ? y : parseFloat(y))));
        const layer = L.polygon(latlngs, { color: section.color_hex || '#00e5ff', fillColor: section.color_hex || '#00e5ff', fillOpacity: section.is_restricted ? 0.08 : 0.03, weight: 1.5, opacity: 0.35 }).addTo(window._map2d);
        layer.bindTooltip(section.name + ' · click to edit', { sticky: true, className: 'holo-tooltip' });
        layer._sectionData = section;
        layer.on('click', (e) => {
          if (_zoneDrawMode || _sectionDrawMode) return;
          L.DomEvent.stopPropagation(e);
          _editSectionOnMap(section);
        });
        _sectionLayers.push(layer);
      });
    }
  } catch (e) { console.warn('Could not load zones:', e); }
}

// ══════════════════════════════════════════════════════════════════════════════
//  TRACKER DOTS
// ══════════════════════════════════════════════════════════════════════════════

let _proximityLayers = [];
let _nearbyTrackerIds = new Set();

function _proximityThresholdM() {
  const v = window.proximityMeters;
  const n = parseFloat(v);
  return Number.isFinite(n) && n > 0 ? n : 2.0;
}

function clearProximityLines() {
  _nearbyTrackerIds = new Set();
  if (window._map2d) {
    _proximityLayers.forEach(l => {
      try { window._map2d.removeLayer(l); } catch (e) {}
    });
  }
  _proximityLayers = [];
}

function renderProximityLines() {
  clearProximityLines();
  if (!window._map2d || !window.selectedTrackerId) return;
  if (window.layerState && window.layerState.proximity === false) return;
  const sel = (window.trackers || {})[window.selectedTrackerId];
  if (!sel || sel.pos_x === undefined || sel.pos_y === undefined) return;
  const threshold = _proximityThresholdM();
  const selPt = L.CRS.Simple.unproject(L.point(sel.pos_x, sel.pos_y));
  Object.values(window.trackers || {}).forEach(t => {
    if (t.id === sel.id || t.pos_x === undefined || t.pos_y === undefined) return;
    const dist = Math.hypot(sel.pos_x - t.pos_x, sel.pos_y - t.pos_y);
    if (dist > threshold) return;
    _nearbyTrackerIds.add(t.id);
    const otherPt = L.CRS.Simple.unproject(L.point(t.pos_x, t.pos_y));
    const line = L.polyline([selPt, otherPt], {
      color: '#ffffff',
      weight: 2,
      opacity: 0.55,
      dashArray: '6,8',
      className: 'proximity-line-leaflet',
    }).addTo(window._map2d);
    line._isProximity = true;
    const name = t.assigned_name || t.hardware_id || '#' + t.id;
    line.bindTooltip(`${dist.toFixed(1)}m · ${name}`, { sticky: true, className: 'holo-tooltip' });
    _proximityLayers.push(line);
  });
  renderTrackerDots();
}

function renderTrackerDots() {
  if (!window._map2d) return;
  window._map2d.eachLayer(l => { if (l._isTrackerDot) window._map2d.removeLayer(l); });
  if (window.layerState && window.layerState.trackers === false) return;
  Object.values(window.trackers || {}).forEach(t => {
    if (t.pos_x === undefined || t.pos_y === undefined) return;
    addTrackerDot(t);
  });
}

function addTrackerDot(t) {
  const latlng = L.CRS.Simple.unproject(L.point(t.pos_x, t.pos_y));
  const dotClass = dotClassForTracker(t);
  const isSelected = window.selectedTrackerId === t.id;
  const isNearby = _nearbyTrackerIds.has(t.id);
  const icon = L.divIcon({ className: '', iconSize: [14, 14], iconAnchor: [7, 7], html: '<div class="tracker-dot ' + dotClass + (isSelected ? ' selected' : '') + (isNearby ? ' nearby' : '') + '" id="dot-' + t.id + '" style="position:relative"></div>' });
  const marker = L.marker(latlng, { icon, zIndexOffset: isSelected ? 1000 : 0 });
  marker._isTrackerDot = true;
  marker.addTo(window._map2d);
  marker.on('click', () => { if (window.selectTracker) window.selectTracker(t.id); });
  const name = t.assigned_name || t.hardware_id || '—';
  const section = t.current_section || t.section_name || '—';
  const speed = t.speed !== null ? ' · ' + t.speed.toFixed(1) + 'm/s' : '';
  const batt = t.battery_level !== undefined ? ' · ' + Math.round(t.battery_level) + '%' : '';
  marker.bindTooltip('<b>' + name + '</b><br>' + section + speed + batt, { direction: 'top', offset: [0, -8], className: 'holo-tooltip' });
}

function updateTrackerDot(tid, pos) {
  if (!window._map2d) return;
  if (window.layerState && window.layerState.trackers === false) return;
  const tracker = window.trackers && window.trackers[tid];
  if (!tracker) return;
  let existing = null;
  window._map2d.eachLayer(l => { if (l._isTrackerDot && l._icon && l._icon.querySelector && l._icon.querySelector('#dot-' + tid)) existing = l; });
  const latlng = L.CRS.Simple.unproject(L.point(pos.x, pos.y));
  if (existing) existing.setLatLng(latlng);
  else addTrackerDot({ ...tracker, pos_x: pos.x, pos_y: pos.y, pos_z: pos.z });
  if (window.selectedTrackerId === tid && window.renderProximityLines) {
    window.renderProximityLines();
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
  window._map2d.setView(L.CRS.Simple.unproject(L.point(x, y)), Math.max(window._map2d.getZoom(), 17), { animate: true });
}

// ── Layer visibility ─────────────────────────────────────────────────────────
function toggleZoneLayer(show) { _zoneLayers.forEach(l => show ? l.addTo(window._map2d) : window._map2d.removeLayer(l)); }
function toggleSectionLayer(show) { _sectionLayers.forEach(l => show ? l.addTo(window._map2d) : window._map2d.removeLayer(l)); }
function toggleGridLayer(show) { _gridLines.forEach(l => show ? l.addTo(window._map2d) : window._map2d.removeLayer(l)); }

// ── Map-native zone draw / section polygon / coverage / trajectory ───────────
let _zoneDrawMode = false;
let _zoneDrawRadius = 5;
let _sectionDrawMode = false;
let _sectionVertices = [];
let _sectionDraftLayer = null;
let _sectionDraftMarkers = [];
let _coverageLayers = [];
let _trajectoryLayer = null;

function enterZoneDrawMode() {
  exitSectionDrawMode();
  _zoneDrawMode = true;
  _mapMode = 'zone_draw';
  if (window.showToast) window.showToast('Click map to place zone center', 'info');
  const btn = document.getElementById('zoneDrawBtn');
  if (btn) btn.classList.add('active');
}

function exitZoneDrawMode() {
  _zoneDrawMode = false;
  if (_mapMode === 'zone_draw') _mapMode = 'normal';
  const btn = document.getElementById('zoneDrawBtn');
  if (btn) btn.classList.remove('active');
  document.getElementById('zoneDrawForm')?.remove();
}

function enterSectionDrawMode() {
  exitZoneDrawMode();
  _sectionDrawMode = true;
  _mapMode = 'section_draw';
  _sectionVertices = [];
  _clearSectionDraft();
  if (window.showToast) window.showToast('Click vertices · Finish when ≥3 points', 'info');
  const btn = document.getElementById('sectionDrawBtn');
  if (btn) btn.classList.add('active');
  _showSectionDrawHint();
}

function exitSectionDrawMode() {
  _sectionDrawMode = false;
  if (_mapMode === 'section_draw') _mapMode = 'normal';
  _sectionVertices = [];
  _clearSectionDraft();
  document.getElementById('sectionDrawHint')?.remove();
  document.getElementById('sectionDrawForm')?.remove();
  const btn = document.getElementById('sectionDrawBtn');
  if (btn) btn.classList.remove('active');
}

function _clearSectionDraft() {
  if (_sectionDraftLayer && window._map2d) {
    try { window._map2d.removeLayer(_sectionDraftLayer); } catch (e) {}
  }
  _sectionDraftLayer = null;
  (_sectionDraftMarkers || []).forEach(m => {
    try { window._map2d.removeLayer(m); } catch (e) {}
  });
  _sectionDraftMarkers = [];
}

function _showSectionDrawHint() {
  document.getElementById('sectionDrawHint')?.remove();
  const mapEl = document.getElementById('map2d');
  if (!mapEl) return;
  const hint = document.createElement('div');
  hint.id = 'sectionDrawHint';
  Object.assign(hint.style, {
    position: 'absolute', top: '16px', left: '50%', transform: 'translateX(-50%)',
    zIndex: '1001', background: 'rgba(8,15,30,0.95)', border: '1px solid rgba(0,229,255,0.35)',
    borderRadius: '10px', padding: '10px 14px', display: 'flex', gap: '10px', alignItems: 'center',
    fontSize: '12px', color: '#c8d6e5', boxShadow: '0 8px 24px rgba(0,0,0,0.45)',
  });
  hint.innerHTML = `
    <span><i class="fa-solid fa-draw-polygon" style="color:#00e5ff;margin-right:6px"></i>
      Section polygon — <strong id="secVertCount">0</strong> vertices</span>
    <button id="secFinishBtn" style="padding:6px 10px;background:#00e5ff;border:none;border-radius:6px;color:#081f3e;font-weight:700;cursor:pointer;font-size:11px">Finish</button>
    <button id="secUndoBtn" style="padding:6px 10px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);border-radius:6px;color:#aaa;cursor:pointer;font-size:11px">Undo</button>
    <button id="secCancelBtn" style="padding:6px 10px;background:none;border:none;color:#888;cursor:pointer;font-size:11px">Cancel</button>
  `;
  mapEl.appendChild(hint);
  hint.querySelector('#secFinishBtn').onclick = () => _finishSectionPolygon();
  hint.querySelector('#secUndoBtn').onclick = () => {
    _sectionVertices.pop();
    _redrawSectionDraft();
  };
  hint.querySelector('#secCancelBtn').onclick = () => exitSectionDrawMode();
}

function _addSectionVertex(latlng) {
  const pt = L.CRS.Simple.project(latlng);
  _sectionVertices.push([pt.x, pt.y]);
  _redrawSectionDraft();
}

function _redrawSectionDraft() {
  _clearSectionDraft();
  const countEl = document.getElementById('secVertCount');
  if (countEl) countEl.textContent = String(_sectionVertices.length);
  if (!_sectionVertices.length || !window._map2d) return;
  const latlngs = _sectionVertices.map(([x, y]) => L.CRS.Simple.unproject(L.point(x, y)));
  if (latlngs.length >= 3) {
    _sectionDraftLayer = L.polygon(latlngs, {
      color: '#00e5ff', fillColor: '#00e5ff', fillOpacity: 0.08, weight: 2, dashArray: '4,4',
    }).addTo(window._map2d);
  } else {
    _sectionDraftLayer = L.polyline(latlngs, {
      color: '#00e5ff', weight: 2, dashArray: '4,4',
    }).addTo(window._map2d);
  }
  latlngs.forEach(ll => {
    const m = L.circleMarker(ll, { radius: 4, color: '#00e5ff', fillColor: '#00e5ff', fillOpacity: 1, weight: 1 });
    m.addTo(window._map2d);
    _sectionDraftMarkers.push(m);
  });
}

function _finishSectionPolygon() {
  if (_sectionVertices.length < 3) {
    if (window.showToast) window.showToast('Need at least 3 vertices', 'error');
    return;
  }
  const polygon = _sectionVertices.map(([x, y]) => [x, y]);
  document.getElementById('sectionDrawHint')?.remove();
  _showSectionForm(polygon);
}

function _showSectionForm(polygon) {
  document.getElementById('sectionDrawForm')?.remove();
  const mapEl = document.getElementById('map2d');
  if (!mapEl) return;
  const panel = document.createElement('div');
  panel.id = 'sectionDrawForm';
  Object.assign(panel.style, {
    position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
    zIndex: '1002', background: 'rgba(8,15,30,0.97)',
    border: '1px solid rgba(0,229,255,0.3)', borderRadius: '14px', padding: '20px 24px',
    width: '360px', maxWidth: '90vw', boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
    backdropFilter: 'blur(12px)', fontFamily: 'var(--font-body, system-ui)',
  });
  panel.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
      <div style="font-size:14px;font-weight:700;color:var(--cyan,#00e5ff)">
        <i class="fa-solid fa-draw-polygon"></i> New Section
      </div>
      <button id="secFormClose" style="background:none;border:none;color:#888;cursor:pointer"><i class="fa-solid fa-xmark"></i></button>
    </div>
    <div style="font-size:11px;color:#aaa;margin-bottom:12px">${polygon.length} vertices</div>
    <label style="font-size:11px;font-weight:700;color:#888;display:block;margin-bottom:6px">NAME *</label>
    <input id="secNameInput" type="text" value="New section"
      style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);border-radius:6px;padding:9px 12px;color:#fff;font-size:14px;outline:none;box-sizing:border-box;margin-bottom:12px">
    <label style="display:flex;align-items:center;gap:8px;font-size:12px;color:#c8d6e5;margin-bottom:12px;cursor:pointer">
      <input type="checkbox" id="secRestrictedInput"> Restricted (alerts on enter)
    </label>
    <label style="font-size:11px;font-weight:700;color:#888;display:block;margin-bottom:6px">COLOR</label>
    <input id="secColorInput" type="color" value="#00e5ff" style="margin-bottom:16px;width:48px;height:32px;border:none;background:transparent">
    <div style="display:flex;gap:8px">
      <button id="secSaveBtn" style="flex:1;padding:9px;background:var(--cyan,#00e5ff);border:none;border-radius:8px;color:#081f3e;font-weight:700;font-size:13px;cursor:pointer">
        <i class="fa-solid fa-floppy-disk"></i> Save Section
      </button>
      <button id="secFormCancel" style="padding:9px 14px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:#888;cursor:pointer">Cancel</button>
    </div>
  `;
  mapEl.appendChild(panel);
  const close = () => exitSectionDrawMode();
  panel.querySelector('#secFormClose').onclick = close;
  panel.querySelector('#secFormCancel').onclick = close;
  panel.querySelector('#secSaveBtn').onclick = async () => {
    const name = (panel.querySelector('#secNameInput').value || '').trim();
    if (!name) { panel.querySelector('#secNameInput').focus(); return; }
    const btn = panel.querySelector('#secSaveBtn');
    btn.disabled = true;
    try {
      const res = await API.post('/zones/sections', {
        name,
        polygon,
        is_restricted: !!panel.querySelector('#secRestrictedInput').checked,
        color_hex: panel.querySelector('#secColorInput').value || '#00e5ff',
      });
      const data = await API.json(res);
      if (res && res.ok) {
        if (window.showToast) window.showToast('Section created', 'success');
        renderZones();
        exitSectionDrawMode();
      } else {
        if (window.showToast) window.showToast((data && data.error) || 'Failed', 'error');
        btn.disabled = false;
      }
    } catch (e) {
      if (window.showToast) window.showToast('Network error', 'error');
      btn.disabled = false;
    }
  };
}

async function _placeZoneAt(latlng) {
  const pt = L.CRS.Simple.project(latlng);
  _showZoneForm(pt.x, pt.y, null);
}

function _editZoneOnMap(zone) {
  const pos = zone.position || { x: zone.pos_x || 0, y: zone.pos_y || 0 };
  _showZoneForm(Number(pos.x) || 0, Number(pos.y) || 0, zone);
}

function _editSectionOnMap(section) {
  // Lightweight section edit form (name / restricted / color)
  document.getElementById('sectionDrawForm')?.remove();
  document.getElementById('zoneDrawForm')?.remove();
  const mapEl = document.getElementById('map2d');
  if (!mapEl) return;
  const panel = document.createElement('div');
  panel.id = 'sectionDrawForm';
  Object.assign(panel.style, {
    position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
    zIndex: '1002', background: 'rgba(8,15,30,0.97)',
    border: '1px solid rgba(0,229,255,0.3)', borderRadius: '14px', padding: '20px 24px',
    width: '360px', maxWidth: '90vw', boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
    backdropFilter: 'blur(12px)', fontFamily: 'var(--font-body, system-ui)',
  });
  panel.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
      <div style="font-size:14px;font-weight:700;color:var(--cyan,#00e5ff)">
        <i class="fa-solid fa-draw-polygon"></i> Edit Section
      </div>
      <button id="secFormClose" style="background:none;border:none;color:#888;cursor:pointer"><i class="fa-solid fa-xmark"></i></button>
    </div>
    <label style="font-size:11px;font-weight:700;color:#888;display:block;margin-bottom:6px">NAME *</label>
    <input id="secNameInput" type="text" value="${(section.name || '').replace(/"/g, '&quot;')}"
      style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);border-radius:6px;padding:9px 12px;color:#fff;font-size:14px;outline:none;box-sizing:border-box;margin-bottom:12px">
    <label style="display:flex;align-items:center;gap:8px;font-size:12px;color:#c8d6e5;margin-bottom:12px;cursor:pointer">
      <input type="checkbox" id="secRestrictedInput" ${section.is_restricted ? 'checked' : ''}> Restricted (alerts on enter)
    </label>
    <label style="font-size:11px;font-weight:700;color:#888;display:block;margin-bottom:6px">COLOR</label>
    <input id="secColorInput" type="color" value="${section.color_hex || '#00e5ff'}" style="margin-bottom:16px;width:48px;height:32px;border:none;background:transparent">
    <div style="display:flex;gap:8px">
      <button id="secSaveBtn" style="flex:1;padding:9px;background:var(--cyan,#00e5ff);border:none;border-radius:8px;color:#081f3e;font-weight:700;font-size:13px;cursor:pointer">
        <i class="fa-solid fa-floppy-disk"></i> Save
      </button>
      <a href="/zones" style="padding:9px 14px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:#aaa;font-size:12px;text-decoration:none;display:inline-flex;align-items:center">List</a>
      <button id="secFormCancel" style="padding:9px 14px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:#888;cursor:pointer">Cancel</button>
    </div>
  `;
  mapEl.appendChild(panel);
  const close = () => panel.remove();
  panel.querySelector('#secFormClose').onclick = close;
  panel.querySelector('#secFormCancel').onclick = close;
  panel.querySelector('#secSaveBtn').onclick = async () => {
    const name = (panel.querySelector('#secNameInput').value || '').trim();
    if (!name) { panel.querySelector('#secNameInput').focus(); return; }
    const btn = panel.querySelector('#secSaveBtn');
    btn.disabled = true;
    try {
      const res = await API.patch('/zones/sections/' + section.id, {
        name,
        is_restricted: !!panel.querySelector('#secRestrictedInput').checked,
        color_hex: panel.querySelector('#secColorInput').value || '#00e5ff',
      });
      const data = await API.json(res);
      if (res && res.ok) {
        if (window.showToast) window.showToast('Section updated', 'success');
        renderZones();
        close();
      } else {
        if (window.showToast) window.showToast((data && data.error) || 'Failed', 'error');
        btn.disabled = false;
      }
    } catch (e) {
      if (window.showToast) window.showToast('Network error', 'error');
      btn.disabled = false;
    }
  };
}

function _showZoneForm(x, y, existing) {
  document.getElementById('zoneDrawForm')?.remove();
  const mapEl = document.getElementById('map2d');
  if (!mapEl) return;
  const isEdit = !!(existing && existing.id);
  const rules = (existing && existing.rules) || {};
  const panel = document.createElement('div');
  panel.id = 'zoneDrawForm';
  Object.assign(panel.style, {
    position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
    zIndex: '1002', background: 'rgba(8,15,30,0.97)',
    border: '1px solid rgba(0,229,255,0.3)', borderRadius: '14px', padding: '20px 24px',
    width: '380px', maxWidth: '90vw', boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
    backdropFilter: 'blur(12px)', fontFamily: 'var(--font-body, system-ui)',
  });
  const nameVal = isEdit ? (existing.name || '') : 'New zone';
  const typeVal = isEdit ? (existing.zone_type || 'RESTRICTED') : 'RESTRICTED';
  const radiusVal = isEdit ? (existing.radius || _zoneDrawRadius) : _zoneDrawRadius;
  const dwellVal = rules.dwell_max_seconds != null ? rules.dwell_max_seconds : '';
  panel.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
      <div style="font-size:14px;font-weight:700;color:var(--cyan,#00e5ff)">
        <i class="fa-solid fa-circle"></i> ${isEdit ? 'Edit Zone' : 'New Zone'}
      </div>
      <button id="zoneFormClose" style="background:none;border:none;color:#888;cursor:pointer"><i class="fa-solid fa-xmark"></i></button>
    </div>
    <div style="font-size:12px;color:#aaa;margin-bottom:14px;padding:8px 10px;background:rgba(0,229,255,0.06);border-radius:6px">
      Center X=${Number(x).toFixed(2)} · Y=${Number(y).toFixed(2)} m
    </div>
    <label style="font-size:11px;font-weight:700;color:#888;display:block;margin-bottom:6px">NAME *</label>
    <input id="zoneNameInput" type="text" value="${String(nameVal).replace(/"/g, '&quot;')}"
      style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);border-radius:6px;padding:9px 12px;color:#fff;font-size:14px;outline:none;box-sizing:border-box;margin-bottom:12px">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px">
      <div>
        <label style="font-size:11px;font-weight:700;color:#888;display:block;margin-bottom:6px">TYPE</label>
        <select id="zoneTypeInput" style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);border-radius:6px;padding:9px 12px;color:#fff;font-size:13px;outline:none">
          ${['RESTRICTED','DANGER','CHECK_IN','CHECK_OUT','NORMAL'].map(t =>
            `<option value="${t}" ${t === typeVal ? 'selected' : ''}>${t}</option>`).join('')}
        </select>
      </div>
      <div>
        <label style="font-size:11px;font-weight:700;color:#888;display:block;margin-bottom:6px">RADIUS (m)</label>
        <input id="zoneRadiusInput" type="number" min="0.5" step="0.5" value="${radiusVal}"
          style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);border-radius:6px;padding:9px 12px;color:#fff;font-size:13px;outline:none;box-sizing:border-box">
      </div>
    </div>
    <div style="border-top:1px solid rgba(255,255,255,0.08);padding-top:12px;margin-bottom:12px">
      <div style="font-size:11px;font-weight:700;color:#888;margin-bottom:8px;letter-spacing:0.06em">RULES</div>
      <label style="font-size:11px;font-weight:700;color:#888;display:block;margin-bottom:6px">DWELL MAX (seconds, blank = none)</label>
      <input id="zoneDwellInput" type="number" min="1" step="1" placeholder="e.g. 120" value="${dwellVal}"
        style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);border-radius:6px;padding:9px 12px;color:#fff;font-size:13px;outline:none;box-sizing:border-box;margin-bottom:10px">
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;color:#c8d6e5;margin-bottom:6px;cursor:pointer">
        <input type="checkbox" id="zoneOnEnterInput" ${rules.on_enter !== false ? 'checked' : ''}> Alert on enter
      </label>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;color:#c8d6e5;cursor:pointer">
        <input type="checkbox" id="zoneOnExitInput" ${rules.on_exit ? 'checked' : ''}> Alert on exit
      </label>
    </div>
    <div style="display:flex;gap:8px">
      <button id="zoneSaveBtn" style="flex:1;padding:9px;background:var(--cyan,#00e5ff);border:none;border-radius:8px;color:#081f3e;font-weight:700;font-size:13px;cursor:pointer">
        <i class="fa-solid fa-floppy-disk"></i> ${isEdit ? 'Save Changes' : 'Save Zone'}
      </button>
      ${isEdit ? `<button id="zoneDeleteBtn" style="padding:9px 12px;background:rgba(248,113,113,.12);border:1px solid rgba(248,113,113,.35);border-radius:8px;color:#fca5a5;cursor:pointer" title="Delete"><i class="fa-solid fa-trash"></i></button>` : ''}
      <button id="zoneFormCancel" style="padding:9px 14px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:#888;cursor:pointer">Cancel</button>
    </div>
  `;
  mapEl.appendChild(panel);
  const close = () => { panel.remove(); exitZoneDrawMode(); };
  panel.querySelector('#zoneFormClose').onclick = close;
  panel.querySelector('#zoneFormCancel').onclick = close;
  const delBtn = panel.querySelector('#zoneDeleteBtn');
  if (delBtn) {
    delBtn.onclick = async () => {
      if (!(await holoConfirm('Delete this zone?', { danger: true, title: 'Confirm' }))) return;
      const res = await API.del('/zones/' + existing.id);
      if (res && res.ok) {
        if (window.showToast) window.showToast('Zone deleted', 'success');
        renderZones();
        close();
      } else if (window.showToast) window.showToast('Delete failed', 'error');
    };
  }
  panel.querySelector('#zoneSaveBtn').onclick = async () => {
    const name = (panel.querySelector('#zoneNameInput').value || '').trim();
    if (!name) { panel.querySelector('#zoneNameInput').focus(); return; }
    const radius = parseFloat(panel.querySelector('#zoneRadiusInput').value) || _zoneDrawRadius;
    const dwellRaw = panel.querySelector('#zoneDwellInput').value;
    const rulesOut = {
      on_enter: !!panel.querySelector('#zoneOnEnterInput').checked,
      on_exit: !!panel.querySelector('#zoneOnExitInput').checked,
      dwell_max_seconds: dwellRaw ? parseFloat(dwellRaw) : null,
    };
    const btn = panel.querySelector('#zoneSaveBtn');
    btn.disabled = true;
    const body = {
      name,
      zone_type: panel.querySelector('#zoneTypeInput').value,
      pos_x: x,
      pos_y: y,
      pos_z: (existing && existing.position && existing.position.z) || 0,
      radius,
      rules: rulesOut,
    };
    try {
      const res = isEdit
        ? await API.patch('/zones/' + existing.id, body)
        : await API.post('/zones', body);
      const data = await API.json(res);
      if (res && res.ok) {
        if (window.showToast) window.showToast(isEdit ? 'Zone updated' : 'Zone created', 'success');
        renderZones();
        close();
      } else {
        if (window.showToast) window.showToast((data && data.error) || 'Failed to save zone', 'error');
        btn.disabled = false;
      }
    } catch (e) {
      if (window.showToast) window.showToast('Network error saving zone', 'error');
      btn.disabled = false;
    }
  };
}

function _nodeCoverageScore(node) {
  // 0–1 confidence from status + heartbeat freshness (no RF model required)
  if (!node) return 0.35;
  const status = String(node.status || '').toUpperCase();
  if (status === 'OFFLINE') return 0.12;
  let score = status === 'ACTIVE' ? 0.85 : (status === 'CALIBRATING' ? 0.55 : 0.4);
  const hb = node.last_heartbeat;
  if (hb) {
    const ageSec = (Date.now() - new Date(hb).getTime()) / 1000;
    if (!Number.isNaN(ageSec)) {
      if (ageSec < 30) score = Math.min(1, score + 0.12);
      else if (ageSec < 120) score *= 0.9;
      else if (ageSec < 600) score *= 0.55;
      else score *= 0.25;
    }
  } else {
    score *= 0.45;
  }
  return Math.max(0.08, Math.min(1, score));
}

function _nodeCoverageRadius(node, score) {
  // Prefer explicit metadata range when present; else scale 6–18 m by confidence
  let base = 12;
  try {
    const meta = typeof node.metadata === 'object' ? node.metadata
      : (node.metadata_json ? JSON.parse(node.metadata_json) : null);
    if (meta && (meta.coverage_radius_m || meta.range_m)) {
      base = Number(meta.coverage_radius_m || meta.range_m) || base;
    }
  } catch (e) {}
  return Math.max(4, base * (0.45 + 0.55 * score));
}

function renderCoverageRings() {
  _coverageLayers.forEach(l => window._map2d.removeLayer(l));
  _coverageLayers = [];
  _nodeMarkers.forEach(m => {
    if (!m.getLatLng) return;
    const node = m._nodeData || {};
    const score = _nodeCoverageScore(node);
    const radius = _nodeCoverageRadius(node, score);
    // Teal → amber → red as confidence drops
    const color = score >= 0.7 ? '#2dd4bf' : (score >= 0.4 ? '#f59e0b' : '#f87171');
    const ring = L.circle(m.getLatLng(), {
      radius,
      color,
      fillColor: color,
      fillOpacity: 0.03 + score * 0.1,
      weight: 1.5,
      opacity: 0.25 + score * 0.45,
      dashArray: score >= 0.55 ? null : '4,6',
    }).addTo(window._map2d);
    ring._isCoverage = true;
    ring.bindTooltip(
      `${node.assigned_name || node.mac_address || 'Anchor'} · coverage ${(score * 100).toFixed(0)}% · r≈${radius.toFixed(1)}m`,
      { direction: 'top', className: 'holo-tooltip' }
    );
    _coverageLayers.push(ring);
  });
}

function toggleCoverageLayer(show) {
  if (show === undefined) show = !(window.layerState && window.layerState.coverage);
  if (!window.layerState) window.layerState = {};
  window.layerState.coverage = !!show;
  if (show) renderCoverageRings();
  else {
    _coverageLayers.forEach(l => window._map2d.removeLayer(l));
    _coverageLayers = [];
  }
}

function showTrajectory(points) {
  if (_trajectoryLayer) {
    window._map2d.removeLayer(_trajectoryLayer);
    _trajectoryLayer = null;
  }
  if (!points || points.length < 2 || !window._map2d) return;
  const latlngs = points.map(p => L.CRS.Simple.unproject(L.point(p.x, p.y)));
  _trajectoryLayer = L.polyline(latlngs, {
    color: '#f59e0b',
    weight: 3,
    opacity: 0.85,
  }).addTo(window._map2d);
  try { window._map2d.fitBounds(_trajectoryLayer.getBounds(), { padding: [40, 40] }); } catch (e) {}
}

function clearTrajectory() {
  if (_trajectoryLayer) {
    window._map2d.removeLayer(_trajectoryLayer);
    _trajectoryLayer = null;
  }
}

window.enterZoneDrawMode = enterZoneDrawMode;
window.exitZoneDrawMode = exitZoneDrawMode;
window.enterSectionDrawMode = enterSectionDrawMode;
window.exitSectionDrawMode = exitSectionDrawMode;
window.toggleCoverageLayer = toggleCoverageLayer;
window.renderCoverageRings = renderCoverageRings;
window.showTrajectory = showTrajectory;
window.clearTrajectory = clearTrajectory;
window.renderProximityLines = renderProximityLines;
window.clearProximityLines = clearProximityLines;
