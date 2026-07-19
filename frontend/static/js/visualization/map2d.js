/**
 * HOLO-RTLS — 2D Floor Plan Map (Leaflet + CRS.Simple)
 *
 * Workflow:
 *  1. Load calibration from /api/positioning/calibration
 *  2. If calibrated: apply affine transform → place nodes by click
 *  3. If not calibrated: 2-point calibration wizard → compute affine transform
 *  4. After calibration: click anywhere = auto real-world coords
 *  5. Node placement mode: click → type name → save
 */
window._map2d = null;
let _floorPlanLayer = null;
let _zoneLayers = [];
let _sectionLayers = [];
let _gridLines = [];
let _nodeMarkers = [];     // Placed node markers on the map

// ── Calibration state ─────────────────────────────────────────────────────────
let _isCalibrated = false;
let _calibrationPoints = [];   // [{pixel_x, pixel_y, real_x, real_y}]
let _imageWidth = 1000;
let _imageHeight = 3000;

// ── Affine transform coefficients ─────────────────────────────────────────────
// real_x = a*x + b*y + c
// real_y = d*x + e*y + f
let _tx_a = 1, _tx_b = 0, _tx_c = 0;   // real_x = a*x + b*y + c
let _ty_d = 0, _ty_e = 1, _ty_f = 0;   // real_y = d*x + e*y + f

// ── Node placement state ──────────────────────────────────────────────────────
let _isNodePlacementMode = false;
let _placementGhost = null;  // temporary marker while placing

// ── Map modes ────────────────────────────────────────────────────────────────
let _mapMode = 'normal';  // 'normal' | 'calibrate' | 'place_node'

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

  L.control.zoom({ position: 'bottomright' }).addTo(window._map2d);
  L.control.scale({ imperial: false, position: 'bottomleft', maxWidth: 200 }).addTo(window._map2d);

  loadCalibration().then(() => {
    loadFloorPlanImage();
    renderZones();
    renderNodeMarkers();
  });

  window._map2d.on('click', onMapClick);
  window._map2d.on('mousemove', onMapMouseMove);

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
}

// ══════════════════════════════════════════════════════════════════════════════
//  COORDINATE TRANSFORMS
// ══════════════════════════════════════════════════════════════════════════════

/**
 * Convert pixel coordinates to real-world coordinates using affine transform.
 * Must have at least 2 calibration points set first.
 * @param {number} px - pixel X
 * @param {number} py - pixel Y (Leaflet uses lat/lng, py maps to image Y)
 */
function pixelToReal(px, py) {
  return {
    x: _tx_a * px + _tx_b * py + _tx_c,
    y: _ty_d * px + _ty_e * py + _ty_f,
  };
}

/**
 * Compute affine transform from 2+ reference points.
 * Uses least-squares best fit.
 * @param {Array<{pixel_x, pixel_y, real_x, real_y}>} points
 */
function computeAffineTransform(points) {
  if (points.length < 2) return;

  if (points.length === 2) {
    // Direct linear transform from 2 points
    // p1 = (x1, y1) → (X1, Y1)
    // p2 = (x2, y2) → (X2, Y2)
    const { pixel_x: x1, pixel_y: y1, real_x: X1, real_y: Y1 } = points[0];
    const { pixel_x: x2, pixel_y: y2, real_x: X2, real_y: Y2 } = points[1];

    // Scale in X and Y independently
    const sx = (X2 - X1) / (x2 - x1);
    const sy = (Y2 - Y1) / (y2 - y1);

    _tx_a = sx;
    _tx_b = 0;
    _tx_c = X1 - sx * x1;

    _ty_d = 0;
    _ty_e = sy;
    _ty_f = Y1 - sy * y1;
  } else {
    // Least-squares fit for overdetermined systems (3+ points)
    // Solve: [x y 1] * [a c]ᵀ = [X]
    //        [x y 1] * [b f]ᵀ = [Y]
    let sum_xx = 0, sum_xy = 0, sum_x = 0;
    let sum_yy = 0, sum_y = 0, sum_n = 0;
    let sum_XX = 0, sum_XY = 0;
    let sum_YX = 0, sum_YY = 0;

    points.forEach(p => {
      const x = p.pixel_x, y = p.pixel_y;
      const X = p.real_x, Y = p.real_y;
      sum_xx += x * x; sum_xy += x * y; sum_x += x;
      sum_yy += y * y; sum_y += y;
      sum_n += 1;
      sum_XX += X * x; sum_XY += X * y;
      sum_YX += Y * x; sum_YY += Y * y;
    });

    // Solve for real_x = a*x + b*y + c
    const det = sum_xx * sum_yy - sum_xy * sum_xy;
    if (Math.abs(det) < 1e-10) return; // degenerate

    _tx_a = (sum_XX * sum_yy - sum_XY * sum_xy) / det;
    _tx_b = (sum_XY * sum_xx - sum_XX * sum_xy) / det;
    _tx_c = (sum_x * sum_XY - sum_XX * sum_y) / det;

    _ty_d = (sum_YX * sum_yy - sum_YY * sum_xy) / det;
    _ty_e = (sum_YY * sum_xx - sum_YX * sum_xy) / det;
    _ty_f = (sum_y * sum_YY - sum_YX * sum_y) / det;
  }

  console.info('[Calibration] Affine transform:', {
    tx: [_tx_a, _tx_b, _tx_c],
    ty: [_ty_d, _ty_e, _ty_f],
  });
}

// ══════════════════════════════════════════════════════════════════════════════
//  CALIBRATION
// ══════════════════════════════════════════════════════════════════════════════

async function loadCalibration() {
  try {
    const res = await API.get('/positioning/calibration');
    const data = await API.json(res);
    if (!res || !res.ok) return;

    const status = data.status || {};
    const cal = status['0'] || status[0] || {};

    if (cal.calibrated && cal.calibration_points && cal.calibration_points.length >= 2) {
      _isCalibrated = true;
      _calibrationPoints = cal.calibration_points;
      computeAffineTransform(_calibrationPoints);
      showCalibrationBadge(true);
      showMapModeIndicator();
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
    position: 'absolute', top: '10px', left: '50%',
    transform: 'translateX(-50%)', zIndex: '1000',
    padding: '6px 14px', borderRadius: '20px',
    fontSize: '12px', fontFamily: 'var(--font-mono, monospace)',
    fontWeight: '600', cursor: 'pointer', pointerEvents: 'auto',
    backdropFilter: 'blur(8px)', transition: 'all 0.2s',
    display: 'flex', alignItems: 'center', gap: '6px',
  });

  if (calibrated) {
    Object.assign(el.style, {
      background: 'rgba(0,229,255,0.12)',
      border: '1px solid rgba(0,229,255,0.4)',
      color: 'var(--cyan, #00e5ff)',
    });
    el.innerHTML = '<i class="fa-solid fa-check-circle"></i> Map calibrated — click to recalibrate';
  } else {
    Object.assign(el.style, {
      background: 'rgba(255,165,0,0.12)',
      border: '1px solid rgba(255,165,0,0.4)',
      color: '#ffa500',
    });
    el.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Calibrate map — click to start';
  }
  el.onclick = enterCalibrationMode;
  const mapEl = document.getElementById('map2d');
  if (mapEl) { mapEl.style.position = 'relative'; mapEl.appendChild(el); }
}

function showMapModeIndicator() {
  // Small corner indicator showing current mode
  const existing = document.getElementById('mapModeIndicator');
  if (existing) existing.remove();

  const el = document.createElement('div');
  el.id = 'mapModeIndicator';
  Object.assign(el.style, {
    position: 'absolute', bottom: '48px', right: '12px', zIndex: '1000',
    background: 'rgba(8,15,30,0.88)', border: '1px solid rgba(0,229,255,0.2)',
    borderRadius: '8px', padding: '5px 10px', fontSize: '11px',
    color: 'var(--text-muted, #888)', display: 'flex', alignItems: 'center', gap: '5px',
    backdropFilter: 'blur(6px)',
  });
  el.innerHTML = '<i class="fa-solid fa-location-crosshairs" style="color:var(--cyan,#00e5ff)"></i> Auto coords active';
  const mapEl = document.getElementById('map2d');
  if (mapEl) mapEl.appendChild(el);
}

function enterCalibrationMode() {
  if (_isNodePlacementMode) exitPlacementMode();
  _mapMode = 'calibrate';
  _calibrationPoints = [];

  // Remove existing form
  document.getElementById('calibrationForm')?.remove();
  document.getElementById('coordReadout')?.remove();

  showCalibrationBadge(false);

  const mapEl = document.getElementById('map2d');
  if (!mapEl) return;
  mapEl.style.position = 'relative';

  // Wizard panel
  const panel = document.createElement('div');
  panel.id = 'calibrationForm';
  Object.assign(panel.style, {
    position: 'absolute', top: '50%', left: '50%',
    transform: 'translate(-50%, -50%)', zIndex: '1001',
    background: 'rgba(8,15,30,0.97)',
    border: '1px solid rgba(0,229,255,0.25)',
    borderRadius: '14px', padding: '20px 24px',
    width: '360px', maxWidth: '90vw',
    boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
    backdropFilter: 'blur(12px)',
    fontFamily: 'var(--font-body, system-ui)',
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
      Click <strong style="color:var(--text-primary,#fff)">2 reference points</strong> on the map.
      For each point, enter its real-world coordinates (shown on your floor plan image).
    </p>
    <div id="calStep1">
      <div style="font-size:11px;font-weight:700;color:var(--text-muted,#888);margin-bottom:8px;letter-spacing:0.06em">POINT 1</div>
      <div style="color:#aaa;font-size:12px;margin-bottom:6px">
        Click on the map where the coordinates are known, then enter them below.
      </div>
      <div id="cal1Info" style="font-size:11px;color:var(--cyan,#00e5ff);margin-bottom:8px;min-height:16px">
        <i class="fa-solid fa-hand-pointer"></i> Click a reference point on the map…
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
        <div>
          <label style="font-size:10px;color:var(--text-muted,#888);display:block;margin-bottom:4px">X (meters)</label>
          <input id="calX1" type="number" step="0.1" placeholder="e.g. -142.5"
            style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);
            border-radius:6px;padding:7px 10px;color:var(--text-primary,#fff);
            font-size:13px;outline:none;box-sizing:border-box">
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-muted,#888);display:block;margin-bottom:4px">Y (meters)</label>
          <input id="calY1" type="number" step="0.1" placeholder="e.g. 87.3"
            style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);
            border-radius:6px;padding:7px 10px;color:var(--text-primary,#fff);
            font-size:13px;outline:none;box-sizing:border-box">
        </div>
      </div>
      <button id="calSave1Btn" disabled
        style="width:100%;padding:8px;background:rgba(0,229,255,0.1);border:1px solid rgba(0,229,255,0.3);
        border-radius:6px;color:var(--text-muted,#888);font-size:12px;cursor:not-allowed;font-weight:600;
        transition:all 0.15s">
        Save Point 1
      </button>
    </div>
    <div id="calStep2" style="display:none;margin-top:16px">
      <div style="font-size:11px;font-weight:700;color:var(--text-muted,#888);margin-bottom:8px;letter-spacing:0.06em">POINT 2</div>
      <div id="cal2Info" style="font-size:11px;color:var(--cyan,#00e5ff);margin-bottom:8px;min-height:16px">
        <i class="fa-solid fa-hand-pointer"></i> Click second reference point…
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
        <div>
          <label style="font-size:10px;color:var(--text-muted,#888);display:block;margin-bottom:4px">X (meters)</label>
          <input id="calX2" type="number" step="0.1" placeholder="e.g. 156.2"
            style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);
            border-radius:6px;padding:7px 10px;color:var(--text-primary,#fff);
            font-size:13px;outline:none;box-sizing:border-box">
        </div>
        <div>
          <label style="font-size:10px;color:var(--text-muted,#888);display:block;margin-bottom:4px">Y (meters)</label>
          <input id="calY2" type="number" step="0.1" placeholder="e.g. 203.8"
            style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);
            border-radius:6px;padding:7px 10px;color:var(--text-primary,#fff);
            font-size:13px;outline:none;box-sizing:border-box">
        </div>
      </div>
      <button id="calSave2Btn" disabled
        style="width:100%;padding:8px;background:rgba(0,229,255,0.1);border:1px solid rgba(0,229,255,0.3);
        border-radius:6px;color:var(--text-muted,#888);font-size:12px;cursor:not-allowed;font-weight:600;
        transition:all 0.15s">
        Save Point 2 &amp; Apply Transform
      </button>
    </div>
    <div id="calDone" style="display:none;text-align:center;padding:16px 0">
      <div style="font-size:24px;margin-bottom:8px">🎉</div>
      <div style="font-size:14px;font-weight:700;color:var(--green,#6bff47);margin-bottom:4px">Calibration Complete!</div>
      <div style="font-size:12px;color:var(--text-muted,#aaa)">
        Click anywhere on the map to auto-place nodes.
      </div>
      <button id="calStartPlacingBtn" style="margin-top:14px;padding:9px 20px;
        background:var(--cyan,#00e5ff);border:none;border-radius:8px;
        color:#081f3e;font-weight:700;font-size:13px;cursor:pointer">
        <i class="fa-solid fa-microchip"></i> Start Placing Nodes
      </button>
    </div>
  `;

  mapEl.appendChild(panel);

  // Close button
  panel.querySelector('#calCloseBtn').onclick = exitCalibrationMode;
  panel.querySelector('#calStartPlacingBtn').onclick = () => {
    exitCalibrationMode();
    enterNodePlacementMode();
  };

  // Enable Save 1 when both coords entered
  const enableSave1 = () => {
    const x = document.getElementById('calX1').value.trim();
    const y = document.getElementById('calY1').value.trim();
    const btn = document.getElementById('calSave1Btn');
    if (x && y) {
      btn.disabled = false;
      btn.style.background = 'rgba(0,229,255,0.15)';
      btn.style.color = 'var(--cyan,#00e5ff)';
      btn.style.cursor = 'pointer';
    } else {
      btn.disabled = true;
      btn.style.background = 'rgba(0,229,255,0.1)';
      btn.style.color = '#666';
      btn.style.cursor = 'not-allowed';
    }
  };
  document.getElementById('calX1').addEventListener('input', enableSave1);
  document.getElementById('calY1').addEventListener('input', enableSave1);

  // Save point 1
  document.getElementById('calSave1Btn').onclick = () => {
    const x = parseFloat(document.getElementById('calX1').value);
    const y = parseFloat(document.getElementById('calY1').value);
    if (isNaN(x) || isNaN(y)) return;

    _calibrationPoints[0] = { real_x: x, real_y: y };
    document.getElementById('cal1Info').innerHTML = `<i class="fa-solid fa-check" style="color:#6bff47"></i> Saved: X=${x}, Y=${y}`;
    document.getElementById('calStep2').style.display = 'block';
    document.getElementById('calStep1').style.opacity = '0.5';
    document.getElementById('cal2Info').innerHTML = '<i class="fa-solid fa-hand-pointer" style="color:#ffa500"></i> Click second reference point on map, then enter coords…';
    // Enable Save 2 when both coords entered
    const enableSave2 = () => {
      const x2 = document.getElementById('calX2').value.trim();
      const y2 = document.getElementById('calY2').value.trim();
      const btn = document.getElementById('calSave2Btn');
      if (x2 && y2) {
        btn.disabled = false;
        btn.style.background = 'rgba(0,229,255,0.15)';
        btn.style.color = 'var(--cyan,#00e5ff)';
        btn.style.cursor = 'pointer';
      }
    };
    document.getElementById('calX2').addEventListener('input', enableSave2);
    document.getElementById('calY2').addEventListener('input', enableSave2);

    // Save point 2
    document.getElementById('calSave2Btn').onclick = async () => {
      const x2 = parseFloat(document.getElementById('calX2').value);
      const y2 = parseFloat(document.getElementById('calY2').value);
      if (isNaN(x2) || isNaN(y2)) return;

      _calibrationPoints[1] = { real_x: x2, real_y: y2 };

      // Compute transform from pixel coords stored during click
      const p1 = _calibrationPoints[0];
      const p2 = _calibrationPoints[1];
      if (!p1._px || !p2._px) {
        alert('Pixel coords not set. Please click both points on the map first.');
        return;
      }
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
      calibration_points: _calibrationPoints,
      calibrated: true,
      section_id: 0,
    });
    _isCalibrated = true;
    showCalibrationBadge(true);
    showMapModeIndicator();
  } catch (e) {
    console.error('Failed to save calibration:', e);
    alert('Failed to save calibration: ' + e.message);
  }
}

// ══════════════════════════════════════════════════════════════════════════════
//  NODE PLACEMENT
// ══════════════════════════════════════════════════════════════════════════════

function enterNodePlacementMode() {
  if (_isCalibrated === false) {
    alert('Please calibrate the map first (2 reference points).');
    enterCalibrationMode();
    return;
  }
  if (_mapMode === 'calibrate') exitCalibrationMode();
  _mapMode = 'place_node';
  _isNodePlacementMode = true;

  // Remove any existing placement UI
  document.getElementById('nodePlacementForm')?.remove();
  document.getElementById('coordReadout')?.remove();
  document.getElementById('nodePlacementBanner')?.remove();

  // Banner at top of map
  const banner = document.createElement('div');
  banner.id = 'nodePlacementBanner';
  Object.assign(banner.style, {
    position: 'absolute', top: '10px', left: '50%', transform: 'translateX(-50%)',
    zIndex: '1000', padding: '7px 16px', borderRadius: '20px',
    background: 'rgba(0,229,255,0.12)', border: '1px solid rgba(0,229,255,0.4)',
    color: 'var(--cyan,#00e5ff)', fontSize: '12px', fontWeight: '600',
    cursor: 'pointer', backdropFilter: 'blur(8px)', display: 'flex',
    alignItems: 'center', gap: '8px', whiteSpace: 'nowrap', zIndex: '1001',
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

  // Coordinate readout at bottom
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
    transition: 'all 0.1s',
  });
  el.innerHTML = `
    <span>X: <strong id="readoutX">—</strong></span>
    <span>Y: <strong id="readoutY">—</strong></span>
    <span style="opacity:0.4">meters</span>
  `;
  const mapEl = document.getElementById('map2d');
  if (mapEl) mapEl.appendChild(el);
}

function showNodeForm(realX, realY, pixelX, pixelY) {
  // Remove existing form
  document.getElementById('nodePlacementForm')?.remove();
  _placementGhost?.remove();

  const mapEl = document.getElementById('map2d');
  if (!mapEl) return;
  mapEl.style.position = 'relative';

  // Ghost marker at click point
  const latlng = L.CRS.Simple.unproject(L.point(pixelX, pixelY));
  _placementGhost = L.circleMarker(latlng, {
    radius: 10, color: '#00e5ff', fillColor: '#00e5ff',
    fillOpacity: 0.5, weight: 2,
  }).addTo(window._map2d);

  const panel = document.createElement('div');
  panel.id = 'nodePlacementForm';
  Object.assign(panel.style, {
    position: 'absolute', top: '50%', left: '50%',
    transform: 'translate(-50%, -50%)', zIndex: '1002',
    background: 'rgba(8,15,30,0.97)',
    border: '1px solid rgba(0,229,255,0.3)',
    borderRadius: '14px', padding: '20px 24px',
    width: '340px', maxWidth: '90vw',
    boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
    backdropFilter: 'blur(12px)',
    fontFamily: 'var(--font-body, system-ui)',
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
      <div><i class="fa-solid fa-location-dot" style="color:var(--cyan,#00e5ff);margin-right:6px;width:14px"></i>
        <strong>X:</strong> ${realX.toFixed(2)} m
        <span style="margin-left:10px"><strong>Y:</strong> ${realY.toFixed(2)} m</span>
      </div>
      <div style="font-size:10px;opacity:0.5">Coordinates auto-calculated from calibration</div>
    </div>

    <div style="margin-bottom:14px">
      <label style="font-size:11px;font-weight:700;color:var(--text-muted,#888);display:block;margin-bottom:6px;letter-spacing:0.05em">NODE NAME *</label>
      <input id="nodeNameInput" type="text" placeholder="e.g. ANCHOR-A1"
        style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);
        border-radius:6px;padding:9px 12px;color:var(--text-primary,#fff);
        font-size:14px;outline:none;box-sizing:border-box">
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:14px">
      <div>
        <label style="font-size:10px;color:var(--text-muted,#888);display:block;margin-bottom:4px">Floor (Z)</label>
        <input id="nodeZInput" type="number" value="0" step="1"
          style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);
          border-radius:6px;padding:7px 10px;color:var(--text-primary,#fff);
          font-size:13px;outline:none;box-sizing:border-box">
      </div>
      <div>
        <label style="font-size:10px;color:var(--text-muted,#888);display:block;margin-bottom:4px">Type</label>
        <select id="nodeTypeInput"
          style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);
          border-radius:6px;padding:7px 10px;color:var(--text-primary,#fff);
          font-size:13px;outline:none;box-sizing:border-box">
          <option value="UWB_ANCHOR">UWB Anchor</option>
          <option value="WIFI_AP">WiFi AP</option>
          <option value="GATEWAY">Gateway</option>
          <option value="REPEATER">Repeater</option>
        </select>
      </div>
      <div>
        <label style="font-size:10px;color:var(--text-muted,#888);display:block;margin-bottom:4px">Section</label>
        <input id="nodeSectionInput" type="text" placeholder="e.g. Shaft A"
          style="width:100%;background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);
          border-radius:6px;padding:7px 10px;color:var(--text-primary,#fff);
          font-size:13px;outline:none;box-sizing:border-box">
      </div>
    </div>

    <div style="display:flex;gap:8px">
      <button id="nodeSaveBtn"
        style="flex:1;padding:9px;background:var(--cyan,#00e5ff);border:none;
        border-radius:8px;color:#081f3e;font-weight:700;font-size:13px;cursor:pointer">
        <i class="fa-solid fa-floppy-disk"></i> Save Node
      </button>
      <button id="nodeCancelBtn"
        style="padding:9px 14px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);
        border-radius:8px;color:var(--text-muted,#888);font-size:13px;cursor:pointer">
        Cancel
      </button>
    </div>
  `;

  mapEl.appendChild(panel);

  // Wire up buttons
  panel.querySelector('#nodeFormClose').onclick = closeNodeForm;
  panel.querySelector('#nodeCancelBtn').onclick = closeNodeForm;

  panel.querySelector('#nodeSaveBtn').onclick = async () => {
    const name = document.getElementById('nodeNameInput').value.trim();
    if (!name) {
      document.getElementById('nodeNameInput').focus();
      return;
    }
    const z = parseFloat(document.getElementById('nodeZInput').value) || 0;
    const type = document.getElementById('nodeTypeInput').value;
    const section = document.getElementById('nodeSectionInput').value.trim();

    const btn = document.getElementById('nodeSaveBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Saving…';

    try {
      const res = await API.post('/nodes', {
        name,
        pos_x: realX,
        pos_y: realY,
        pos_z: z,
        node_type: type,
        section_name: section || null,
      });
      if (res && res.ok) {
        const data = await API.json(res);
        closeNodeForm();
        await renderNodeMarkers();
        // Highlight the new node
        if (data.node && window.showToast) {
          window.showToast(`Node "${name}" placed at X=${realX.toFixed(1)}, Y=${realY.toFixed(1)}`, 'success');
        }
      } else {
        const err = await API.json(res);
        alert('Failed to save node: ' + (err?.error || res.statusText));
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Node';
      }
    } catch (e) {
      alert('Error saving node: ' + e.message);
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Node';
    }
  };

  // Enter key saves
  document.getElementById('nodeNameInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') panel.querySelector('#nodeSaveBtn').click();
    if (e.key === 'Escape') closeNodeForm();
  });
  document.getElementById('nodeNameInput').focus();
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
  // Get pixel coordinates on the image
  // Leaflet CRS.Simple: containerPoint is relative to map container
  // We need pixel coords relative to the image overlay
  const containerPoint = e.containerPoint;
  const px = containerPoint.x;
  const py = containerPoint.y;

  if (_mapMode === 'calibrate') {
    handleCalibrationClick(px, py, e);
  } else if (_mapMode === 'place_node') {
    handleNodePlacementClick(px, py, e);
  }
}

function handleCalibrationClick(px, py, e) {
  // Store pixel coords for the current calibration point
  const step1Empty = !_calibrationPoints[0]?._px;
  const step2Empty = !_calibrationPoints[1]?._px;

  if (step1Empty) {
    // First click — store pixel coords
    _calibrationPoints[0] = { _px: px, _py: py, real_x: 0, real_y: 0 };
    document.getElementById('cal1Info').innerHTML =
      `<i class="fa-solid fa-check" style="color:#6bff47"></i> Clicked at pixel (${Math.round(px)}, ${Math.round(py)}) — enter coords below`;
    // Enable the X1 input focus
    setTimeout(() => document.getElementById('calX1')?.focus(), 50);
  } else if (step2Empty) {
    // Second click
    _calibrationPoints[1] = { _px: px, _py: py, real_x: 0, real_y: 0 };
    document.getElementById('cal2Info').innerHTML =
      `<i class="fa-solid fa-check" style="color:#6bff47"></i> Clicked at pixel (${Math.round(px)}, ${Math.round(py)}) — enter coords below`;
    setTimeout(() => document.getElementById('calX2')?.focus(), 50);
  } else {
    // Already have 2 points — inform user to save first
    document.getElementById('cal2Info').innerHTML =
      `<i class="fa-solid fa-info-circle" style="color:#ffa500"></i> Save Point 2 first, then click to re-calibrate`;
  }
}

function handleNodePlacementClick(px, py, e) {
  if (!_isCalibrated) {
    enterCalibrationMode();
    return;
  }

  const real = pixelToReal(px, py);

  // Update coordinate preview in banner
  const preview = document.getElementById('coordPreview');
  if (preview) preview.textContent = `X=${real.x.toFixed(1)}  Y=${real.y.toFixed(1)}`;

  // Show the node form
  showNodeForm(real.x, real.y, px, py);
}

function onMapMouseMove(e) {
  if (_mapMode !== 'place_node' && _mapMode !== 'normal') return;

  const containerPoint = e.containerPoint;
  const px = containerPoint.x;
  const py = containerPoint.y;

  // Update coordinate readout
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

  // Update banner coord preview
  if (_isNodePlacementMode) {
    const preview = document.getElementById('coordPreview');
    if (preview) {
      const real = _isCalibrated ? pixelToReal(px, py) : { x: Math.round(px), y: Math.round(py) };
      preview.textContent = `X=${real.x.toFixed(1)}  Y=${real.y.toFixed(1)}`;
    }
  }
}

// ══════════════════════════════════════════════════════════════════════════════
//  NODE MARKERS (render placed nodes on map)
// ══════════════════════════════════════════════════════════════════════════════

async function renderNodeMarkers() {
  // Remove old markers
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

      const typeIconMap = {
        UWB_ANCHOR: 'fa-wifi',
        WIFI_AP: 'fa-wifi',
        GATEWAY: 'fa-tower-cell',
        REPEATER: 'fa-repeat',
      };
      const icon = typeIconMap[node.node_type] || 'fa-microchip';
      const label = node.assigned_name || node.mac_address || 'Node';: filled circle with type icon
      const nodeIcon = L.divIcon({
        className: '',
        html: `<div class="node-marker" data-id="${node.id}">
          <div class="node-icon-wrap">
            <i class="fa-solid ${icon}"></i>
          </div>
          <div class="node-label">${node.name || node.hardware_id || 'Node'}</div>
        </div>`,
        iconSize: [32, 32],
        iconAnchor: [16, 16],
      });

      const marker = L.marker(latlng, { icon: nodeIcon, zIndexOffset: 500 });
      marker._isNodeMarker = true;
      marker._nodeId = node.id;

      marker.bindTooltip(`<b>${node.name || node.hardware_id}</b><br>${node.node_type || ''}`, {
        direction: 'top', offset: [0, -18], className: 'holo-tooltip',
      });

      marker.on('click', () => {
        if (_isNodePlacementMode) {
          exitPlacementMode();
        }
        // Show node detail popup
        showNodeDetail(node);
      });

      marker.addTo(window._map2d);
      _nodeMarkers.push(marker);
    });
  } catch (e) {
    console.warn('Could not render node markers:', e);
  }
}

function showNodeDetail(node) {
  // Simple info popup — could expand to an edit form
  const latlng = L.CRS.Simple.unproject(L.point(node.pos_x, node.pos_y));
  L.popup({ className: 'holo-popup' })
    .setLatLng(latlng)
    .setContent(`
      <div style="font-family:var(--font-body,system-ui);min-width:180px">
        <div style="font-size:13px;font-weight:700;color:var(--cyan,#00e5ff);margin-bottom:6px">
          <i class="fa-solid fa-microchip"></i> ${node.name || node.hardware_id || 'Node'}
        </div>
        <div style="font-size:11px;color:#aaa;line-height:1.8">
          <div><strong>Type:</strong> ${node.node_type || '—'}</div>
          <div><strong>X:</strong> ${(node.pos_x ?? node.position?.x)?.toFixed(2) || '—'} m</div>
          <div><strong>Y:</strong> ${(node.pos_y ?? node.position?.y)?.toFixed(2) || '—'} m</div>
          <div><strong>Z:</strong> ${node.pos_z ?? node.position?.z ?? 0} (floor)</div>
          ${node.section_name ? `<div><strong>Section:</strong> ${node.section_name}</div>` : ''}
          <div><strong>Status:</strong> <span style="color:${node.is_active !== false ? '#6bff47' : '#ff4444'}">${node.is_active !== false ? 'Active' : 'Inactive'}</span></div>
        </div>
      </div>
    `)
    .openOn(window._map2d);
}

// ══════════════════════════════════════════════════════════════════════════════
//  FLOOR PLAN IMAGE
// ══════════════════════════════════════════════════════════════════════════════

async function loadFloorPlanImage() {
  if (_floorPlanLayer) {
    window._map2d.removeLayer(_floorPlanLayer);
    _floorPlanLayer = null;
  }

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
  loadFloorPlanFromURL('/static/assets/floor-plan-placeholder.png', null);
}

function loadFloorPlanFromURL(url, section) {
  const img = new Image();
  img.onload = () => {
    _imageWidth = img.naturalWidth || 1000;
    _imageHeight = img.naturalHeight || 1000;

    let southWest, northEast;
    if (_isCalibrated && _calibrationPoints.length >= 2) {
      // Use calibration for real-world bounds
      const allRealX = _calibrationPoints.map(p => p.real_x);
      const allRealY = _calibrationPoints.map(p => p.real_y);
      const minX = Math.min(...allRealX);
      const maxX = Math.max(...allRealX);
      const minY = Math.min(...allRealY);
      const maxY = Math.max(...allRealY);
      // Y in Leaflet is inverted (lat increases up, image Y increases down)
      southWest = [_imageHeight - maxY, minX];
      northEast = [_imageHeight - minY, maxX];
    } else {
      southWest = [_imageHeight, 0];
      northEast = [0, _imageWidth];
    }

    _floorPlanLayer = L.imageOverlay(url, [southWest, northEast], {
      opacity: 0.92,
      crossOrigin: true,
    }).addTo(window._map2d);

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
    const latlng1 = L.CRS.Simple.unproject(L.point(x, 0));
    const latlng2 = L.CRS.Simple.unproject(L.point(x, _imageHeight || 1000));
    const line = L.polyline([latlng1, latlng2], {
      color: 'rgba(0,229,255,0.08)', weight: 1,
    }).addTo(window._map2d);
    _gridLines.push(line);
  }
  for (let y = 0; y <= (_imageHeight || 1000); y += step) {
    const latlng1 = L.CRS.Simple.unproject(L.point(0, y));
    const latlng2 = L.CRS.Simple.unproject(L.point(_imageWidth || 1000, y));
    const line = L.polyline([latlng1, latlng2], {
      color: 'rgba(0,229,255,0.08)', weight: 1,
    }).addTo(window._map2d);
    _gridLines.push(line);
  }
}

async function renderZones() {
  _zoneLayers.forEach(l => window._map2d.removeLayer(l));
  _sectionLayers.forEach(l => window._map2d.removeLayer(l));
  _zoneLayers = [];
  _sectionLayers = [];

  try {
    const zRes = await API.get('/zones');
    const zData = await API.json(zRes);
    if (zRes && zRes.ok && zData.items) {
      zData.items.forEach(zone => {
        const pos = zone.position || { x: zone.pos_x || 0, y: zone.pos_y || 0 };
        const latlng = L.CRS.Simple.unproject(L.point(pos.x, pos.y));

        const colorMap = {
          RESTRICTED: { color: '#ff4444', fill: '#ff4444' },
          DANGER: { color: '#ff6b35', fill: '#ff6b35' },
          CHECK_IN: { color: '#00e5ff', fill: '#00e5ff' },
          CHECK_OUT: { color: '#00e5ff', fill: '#00e5ff' },
          NORMAL: { color: '#00e5ff', fill: '#00e5ff' },
        };
        const c = colorMap[zone.zone_type] || colorMap.NORMAL;

        const layer = L.circle(latlng, {
          radius: zone.radius || 5,
          color: c.color, fillColor: c.fill,
          fillOpacity: 0.06,
          weight: zone.zone_type === 'RESTRICTED' ? 2 : 1,
          opacity: zone.zone_type === 'RESTRICTED' ? 0.7 : 0.3,
          dashArray: zone.zone_type === 'DANGER' ? '6,4' : null,
        }).addTo(window._map2d);

        layer.bindTooltip(zone.name, { permanent: false, direction: 'top', className: 'holo-tooltip' });
        _zoneLayers.push(layer);
      });
    }

    const sRes = await API.get('/zones/sections');
    const sData = await API.json(sRes);
    if (sRes && sRes.ok && sData.items) {
      sData.items.forEach(section => {
        const coords = section.polygon;
        if (!coords || !Array.isArray(coords) || coords.length < 3) return;

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
          weight: 1.5, opacity: 0.35,
        }).addTo(window._map2d);

        layer.bindTooltip(section.name, { sticky: true, className: 'holo-tooltip' });
        _sectionLayers.push(layer);
      });
    }
  } catch (e) {
    console.warn('Could not load zones:', e);
  }
}

// ══════════════════════════════════════════════════════════════════════════════
//  TRACKER DOTS
// ══════════════════════════════════════════════════════════════════════════════

function renderTrackerDots() {
  if (!window._map2d) return;
  window._map2d.eachLayer(layer => {
    if (layer._isTrackerDot) window._map2d.removeLayer(layer);
  });
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

  marker.on('click', () => { if (window.selectTracker) window.selectTracker(t.id); });

  const name = t.assigned_name || t.hardware_id || '—';
  const section = t.current_section || t.section_name || '—';
  const speed = t.speed !== null ? ` · ${t.speed.toFixed(1)}m/s` : '';
  const batt = t.battery_level !== undefined ? ` · ${Math.round(t.battery_level)}%` : '';
  marker.bindTooltip(`<b>${name}</b><br>${section}${speed}${batt}`, {
    direction: 'top', offset: [0, -8], className: 'holo-tooltip',
  });
}

function updateTrackerDot(tid, pos) {
  if (!window._map2d) return;
  if (window.layerState && window.layerState.trackers === false) return;

  const tracker = window.trackers && window.trackers[tid];
  if (!tracker) return;

  let existing = null;
  window._map2d.eachLayer(layer => {
    if (layer._isTrackerDot &&
        layer._icon?.querySelector?.(`#dot-${tid}`)) {
      existing = layer;
    }
  });

  const latlng = L.CRS.Simple.unproject(L.point(pos.x, pos.y));
  if (existing) {
    existing.setLatLng(latlng);
  } else {
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

// ── Layer visibility ─────────────────────────────────────────────────────────
function toggleZoneLayer(show) {
  _zoneLayers.forEach(l => show ? l.addTo(window._map2d) : window._map2d.removeLayer(l));
}
function toggleSectionLayer(show) {
  _sectionLayers.forEach(l => show ? l.addTo(window._map2d) : window._map2d.removeLayer(l));
}
function toggleGridLayer(show) {
  _gridLines.forEach(l => show ? l.addTo(window._map2d) : window._map2d.removeLayer(l));
}
