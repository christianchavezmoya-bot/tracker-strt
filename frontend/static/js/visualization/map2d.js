/**
 * HOLO-RTLS — 2D Floor Plan Map (Leaflet)
 */
let map2d = null;
const MAP_CENTER = [0, 0];
const MAP_ZOOM = 16;

function initMap2D() {
  const container = document.getElementById('map2d');

  map2d = L.map('map2d', {
    center: MAP_CENTER,
    zoom: MAP_ZOOM,
    zoomControl: false,
    crs: L.CRS.Simple,   // Flat 2D coordinate system (not geographic)
    minZoom: 10,
    maxZoom: 22,
  });

  // ── Floor plan image overlay ─────────────────────────────────────────────
  // Replace the URL below with your CAD floor plan image
  // For demo, show a placeholder grid
  const bounds = [[0, 0], [1000, 1000]];

  L.imageOverlay('/static/assets/floor-plan-placeholder.png', bounds, {
    opacity: 0.9,
  }).addTo(map2d);

  map2d.fitBounds(bounds);

  // ── Placeholder grid for demo (remove when real CAD is loaded) ───────────
  for (let x = 0; x <= 1000; x += 100) {
    L.polyline([[0, x], [1000, x]], { color: 'rgba(0,229,255,0.06)', weight: 1 }).addTo(map2d);
    L.polyline([[x, 0], [x, 1000]], { color: 'rgba(0,229,255,0.06)', weight: 1 }).addTo(map2d);
  }

  // ── Tracker dot layer ────────────────────────────────────────────────────
  renderTrackerDots();

  // ── Zone layer ───────────────────────────────────────────────────────────
  loadAndRenderZones();

  // ── Scale bar ────────────────────────────────────────────────────────────
  L.control.scale({ imperial: false, position: 'bottomleft' }).addTo(map2d);
}

// ── Render tracker dots on map ────────────────────────────────────────────────
function renderTrackerDots() {
  if (!map2d) return;
  // Remove existing dot markers
  map2d.eachLayer(layer => {
    if (layer._isTrackerDot) map2d.removeLayer(layer);
  });

  trackers.forEach(t => {
    if (t.pos_x === undefined || t.pos_y === undefined) return;
    // Leaflet CRS.Simple uses [y, x] for coordinates
    const latlng = [t.pos_y, t.pos_x];
    const dotClass = alertDotClass(t.alert_status, t.asset_state);

    const icon = L.divIcon({
      className: '',
      html: `<div class="tracker-dot ${dotClass} ${selectedTrackerId === t.id ? 'selected' : ''}"
                   id="dot-${t.id}" style="position:relative"></div>`,
      iconSize: [14, 14],
      iconAnchor: [7, 7],
    });

    const marker = L.marker(latlng, { icon }).addTo(map2d);
    marker._isTrackerDot = true;
    marker.on('click', () => selectTracker(t.id));
    marker.bindTooltip(
      `<b>${t.assigned_name || t.hardware_id}</b><br>${t.category}<br>${t.current_section || '—'}`,
      { direction: 'top', offset: [0, -8], className: 'holo-tooltip' }
    );
  });
}

// ── Load and render zones ──────────────────────────────────────────────────────
async function loadAndRenderZones() {
  try {
    const res = await API.get('/zones');
    const data = await API.json(res);
    if (!res || !res.ok || !data.items) return;

    data.items.forEach(zone => {
      if (zone.zone_type === 'NORMAL' || zone.zone_type === 'CHECK_IN' || zone.zone_type === 'CHECK_OUT') return;
      // Restricted zone — draw a circle
      const ring = L.circle([zone.pos_y, zone.pos_x], {
        radius: zone.radius,
        color: zone.zone_type === 'RESTRICTED' ? '#ff4444' : '#ffb300',
        fillColor: zone.zone_type === 'RESTRICTED' ? '#ff4444' : '#ffb300',
        fillOpacity: 0.08,
        weight: 2,
        opacity: 0.4,
        dashArray: zone.zone_type === 'DANGER' ? '8,4' : null,
      }).addTo(map2d);
    });

    // Render section polygons
    const secRes = await API.get('/zones/sections');
    const secData = await API.json(secRes);
    if (secRes && secRes.ok && secData.items) {
      secData.items.forEach(section => {
        const polygon = JSON.parse(section.polygon_json);
        if (!polygon || polygon.length < 3) return;
        const coords = polygon.map(p => [p[1], p[0]]);   // [y, x]
        L.polygon(coords, {
          color: section.color_hex || '#00e5ff',
          fillColor: section.color_hex || '#00e5ff',
          fillOpacity: section.is_restricted ? 0.1 : 0.05,
          weight: 1.5,
          opacity: 0.3,
        }).addTo(map2d).bindTooltip(section.name, { sticky: true });
      });
    }
  } catch (e) {
    console.warn('Could not load zones:', e);
  }
}
