/**
 * HOLO-RTLS — Regional / georeferenced map (OpenStreetMap + GPS tie-points)
 * Used before mine-grid calibration or for site-context view with street map layer.
 */
window.MapGeoref = (function () {
  'use strict';

  const OSM = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
  const SAT = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

  let siteLat = -25.2744;
  let siteLng = 133.7751;
  let siteZoom = 5;
  let siteCountry = 'Australia';
  let viewMode = 'mine'; // 'regional' | 'mine'
  let isGeoref = false;
  let georefPoints = [];
  let geoAffine = null;
  let streetLayer = null;
  let satelliteLayer = null;
  let geoImageLayer = null;
  let activeBasemap = 'street'; // street | satellite

  function computeAffine(points, xKey, yKey) {
    if (!points || points.length < 2) return null;
    if (points.length === 2) {
      const p1 = points[0];
      const p2 = points[1];
      const x1 = p1.pixel_x;
      const y1 = p1.pixel_y;
      const x2 = p2.pixel_x;
      const y2 = p2.pixel_y;
      const X1 = p1[xKey];
      const Y1 = p1[yKey];
      const X2 = p2[xKey];
      const Y2 = p2[yKey];
      const dx = x2 - x1;
      const dy = y2 - y1;
      if (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9) return null;
      return {
        a: Math.abs(dx) > 1e-9 ? (X2 - X1) / dx : 0,
        b: 0,
        c: X1 - (Math.abs(dx) > 1e-9 ? (X2 - X1) / dx : 0) * x1,
        d: 0,
        e: Math.abs(dy) > 1e-9 ? (Y2 - Y1) / dy : 0,
        f: Y1 - (Math.abs(dy) > 1e-9 ? (Y2 - Y1) / dy : 0) * y1,
      };
    }
    let sum_xx = 0, sum_xy = 0, sum_x = 0, sum_yy = 0, sum_y = 0, sum_n = 0;
    let sum_XX = 0, sum_XY = 0, sum_YX = 0, sum_YY = 0;
    points.forEach(p => {
      sum_xx += p.pixel_x * p.pixel_x;
      sum_xy += p.pixel_x * p.pixel_y;
      sum_x += p.pixel_x;
      sum_yy += p.pixel_y * p.pixel_y;
      sum_y += p.pixel_y;
      sum_n++;
      sum_XX += p[xKey] * p.pixel_x;
      sum_XY += p[xKey] * p.pixel_y;
      sum_YX += p[yKey] * p.pixel_x;
      sum_YY += p[yKey] * p.pixel_y;
    });
    const det = sum_xx * sum_yy - sum_xy * sum_xy;
    if (Math.abs(det) < 1e-10) return null;
    return {
      a: (sum_XX * sum_yy - sum_XY * sum_xy) / det,
      b: (sum_XY * sum_xx - sum_XX * sum_xy) / det,
      c: (sum_x * sum_XY - sum_XX * sum_y) / det,
      d: (sum_YX * sum_yy - sum_YY * sum_xy) / det,
      e: (sum_YY * sum_xx - sum_YX * sum_xy) / det,
      f: (sum_y * sum_YY - sum_YX * sum_y) / det,
    };
  }

  function applyAffine(aff, px, py) {
    return {
      x: aff.a * px + aff.b * py + aff.c,
      y: aff.d * px + aff.e * py + aff.f,
    };
  }

  async function loadSiteContext() {
    try {
      const res = await API.get('/positioning/map-context');
      const data = await API.json(res);
      if (res && res.ok && data) {
        siteLat = Number(data.site_lat) || siteLat;
        siteLng = Number(data.site_lng) || siteLng;
        siteZoom = Number(data.site_zoom) || siteZoom;
        siteCountry = data.country || siteCountry;
        if (Array.isArray(data.georef_points) && data.georef_points.length >= 2) {
          loadGeorefPoints(data.georef_points);
        }
      }
    } catch (e) {
      console.warn('[MapGeoref] map-context load failed', e);
    }
  }

  function loadGeorefPoints(points) {
    georefPoints = (points || []).map(p => ({
      pixel_x: Number(p.pixel_x),
      pixel_y: Number(p.pixel_y),
      lat: Number(p.lat),
      lng: Number(p.lng),
    }));
    isGeoref = georefPoints.length >= 2;
    geoAffine = isGeoref ? computeAffine(georefPoints, 'lat', 'lng') : null;
  }

  function pixelToLatLng(px, py) {
    if (!geoAffine) return null;
    const r = applyAffine(geoAffine, px, py);
    return { lat: r.x, lng: r.y };
  }

  function georefImageBounds(imageWidth, imageHeight) {
    if (!isGeoref || !geoAffine) return null;
    const corners = [
      [0, 0], [imageWidth, 0], [imageWidth, imageHeight], [0, imageHeight],
    ];
    const lats = [];
    const lngs = [];
    corners.forEach(([px, py]) => {
      const ll = pixelToLatLng(px, py);
      if (ll) {
        lats.push(ll.lat);
        lngs.push(ll.lng);
      }
    });
    if (lats.length < 4) return null;
    return L.latLngBounds([
      [Math.min(...lats), Math.min(...lngs)],
      [Math.max(...lats), Math.max(...lngs)],
    ]);
  }

  function _addBasemap(map) {
    streetLayer = L.tileLayer(OSM, {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    });
    satelliteLayer = L.tileLayer(SAT, {
      attribution: '&copy; Esri',
      maxZoom: 19,
    });
    const wantSat = window.layerState && window.layerState.satelliteMap;
    const wantStreet = !wantSat && (!window.layerState || window.layerState.streetMap !== false);
    if (wantSat) {
      satelliteLayer.addTo(map);
      activeBasemap = 'satellite';
    } else if (wantStreet) {
      streetLayer.addTo(map);
      activeBasemap = 'street';
    }
  }

  function createRegionalMap() {
    const el = document.getElementById('map2d');
    if (!el) return null;
    el.innerHTML = '';
    const map = L.map(el, {
      center: [siteLat, siteLng],
      zoom: siteZoom,
      zoomControl: false,
      maxZoom: 19,
      attributionControl: true,
    });
    _addBasemap(map);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.control.scale({ imperial: false, position: 'bottomleft', maxWidth: 200 }).addTo(map);
    viewMode = 'regional';
    return map;
  }

  function overlayFloorPlan(map, url, imageWidth, imageHeight) {
    if (geoImageLayer) {
      map.removeLayer(geoImageLayer);
      geoImageLayer = null;
    }
    if (!url || !isGeoref) {
      map.setView([siteLat, siteLng], siteZoom, { animate: false });
      return null;
    }
    const bounds = georefImageBounds(imageWidth, imageHeight);
    if (!bounds) {
      map.setView([siteLat, siteLng], siteZoom, { animate: false });
      return null;
    }
    geoImageLayer = L.imageOverlay(url, bounds, {
      opacity: window.getFloorPlanOpacity ? window.getFloorPlanOpacity() : 0.85,
      crossOrigin: true,
    }).addTo(map);
    map.fitBounds(bounds, { padding: [32, 32], maxZoom: 17, animate: false });
    return geoImageLayer;
  }

  function toggleStreetLayer(show) {
    if (!window._map2d || viewMode !== 'regional') return;
    if (show === undefined) show = !(streetLayer && window._map2d.hasLayer(streetLayer));
    if (show) {
      if (satelliteLayer && window._map2d.hasLayer(satelliteLayer)) {
        window._map2d.removeLayer(satelliteLayer);
      }
      if (streetLayer && !window._map2d.hasLayer(streetLayer)) streetLayer.addTo(window._map2d);
      activeBasemap = 'street';
    } else if (streetLayer && window._map2d.hasLayer(streetLayer)) {
      window._map2d.removeLayer(streetLayer);
    }
    if (!window.layerState) window.layerState = {};
    window.layerState.streetMap = !!show;
  }

  function toggleSatelliteLayer(show) {
    if (!window._map2d || viewMode !== 'regional') return;
    if (show === undefined) show = !(satelliteLayer && window._map2d.hasLayer(satelliteLayer));
    if (show) {
      if (streetLayer && window._map2d.hasLayer(streetLayer)) {
        window._map2d.removeLayer(streetLayer);
      }
      if (satelliteLayer && !window._map2d.hasLayer(satelliteLayer)) satelliteLayer.addTo(window._map2d);
      activeBasemap = 'satellite';
    } else if (satelliteLayer && window._map2d.hasLayer(satelliteLayer)) {
      window._map2d.removeLayer(satelliteLayer);
    }
    if (!window.layerState) window.layerState = {};
    window.layerState.satelliteMap = !!show;
  }

  function showRegionalBanner(message) {
    let el = document.getElementById('regionalMapBanner');
    if (!el) {
      el = document.createElement('div');
      el.id = 'regionalMapBanner';
      Object.assign(el.style, {
        position: 'absolute', top: '12px', left: '50%', transform: 'translateX(-50%)',
        zIndex: '25', padding: '8px 14px', borderRadius: '10px', fontSize: '12px',
        background: 'rgba(10,132,255,0.15)', border: '1px solid rgba(10,132,255,0.45)',
        color: '#5eead4', backdropFilter: 'blur(8px)', maxWidth: '90%', textAlign: 'center',
      });
      const mapEl = document.getElementById('map2d');
      if (mapEl && mapEl.parentElement) mapEl.parentElement.appendChild(el);
    }
    el.textContent = message;
    el.style.display = 'block';
  }

  function hideRegionalBanner() {
    const el = document.getElementById('regionalMapBanner');
    if (el) el.style.display = 'none';
  }

  async function saveGeorefPoints(points) {
    const res = await API.post('/positioning/calibration', {
      georef_points: points.map(p => ({
        pixel_x: p.pixel_x,
        pixel_y: p.pixel_y,
        lat: p.lat,
        lng: p.lng,
      })),
      section_id: 0,
    });
    const data = await API.json(res);
    if (res && res.ok) {
      loadGeorefPoints(data.georef_points || points);
      return true;
    }
    return false;
  }

  function setFloorPlanOpacity(opacity) {
    const op = Math.max(0.1, Math.min(1, parseFloat(opacity) || 0.85));
    if (geoImageLayer && typeof geoImageLayer.setOpacity === 'function') {
      geoImageLayer.setOpacity(op);
    }
  }

  return {
    loadSiteContext,
    loadGeorefPoints,
    pixelToLatLng,
    georefImageBounds,
    createRegionalMap,
    overlayFloorPlan,
    setFloorPlanOpacity,
    toggleStreetLayer,
    toggleSatelliteLayer,
    showRegionalBanner,
    hideRegionalBanner,
    saveGeorefPoints,
    getSiteCenter: () => ({ lat: siteLat, lng: siteLng, zoom: siteZoom, country: siteCountry }),
    isGeoref: () => isGeoref,
    getGeorefPoints: () => georefPoints.slice(),
    getViewMode: () => viewMode,
    setViewMode: (m) => { viewMode = m; },
  };
})();
