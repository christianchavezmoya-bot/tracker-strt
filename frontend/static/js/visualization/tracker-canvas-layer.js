/**
 * HOLO-RTLS — High-performance tracker canvas layer (ADR-001)
 * Renders hundreds of tags in a single canvas draw call on Leaflet maps.
 */
'use strict';

window.TrackerCanvasLayer = L.Layer.extend({
  initialize(options) {
    L.setOptions(this, options);
    this._trackers = {};
    this._selectedId = null;
    this._dotRadius = 7;
    this._hitRadius = 12;
  },

  onAdd(map) {
    this._map = map;
    const pane = map.getPane('overlayPane');
    this._canvas = L.DomUtil.create('canvas', 'tracker-canvas-layer');
    this._canvas.style.position = 'absolute';
    this._canvas.style.pointerEvents = 'auto';
    this._canvas.style.zIndex = '650';
    pane.appendChild(this._canvas);
    this._ctx = this._canvas.getContext('2d');

    this._redraw = this._redraw.bind(this);
    map.on('move zoom resize viewreset', this._redraw, this);
    this._canvas.addEventListener('click', this._onClick.bind(this));
    this._redraw();
  },

  onRemove(map) {
    map.off('move zoom resize viewreset', this._redraw, this);
    L.DomUtil.remove(this._canvas);
    this._canvas = null;
    this._ctx = null;
  },

  setTrackers(trackers) {
    this._trackers = trackers || {};
    this._redraw();
  },

  setSelectedId(id) {
    this._selectedId = id;
    this._redraw();
  },

  updateTracker(id, pos) {
    const t = this._trackers[id];
    if (!t) return;
    t.pos_x = pos.x;
    t.pos_y = pos.y;
    if (pos.z != null) t.pos_z = pos.z;
    this._redraw();
  },

  _resizeCanvas() {
    if (!this._map || !this._canvas) return;
    const size = this._map.getSize();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this._canvas.width = Math.floor(size.x * dpr);
    this._canvas.height = Math.floor(size.y * dpr);
    this._canvas.style.width = size.x + 'px';
    this._canvas.style.height = size.y + 'px';
    this._ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  },

  _colorForTracker(t) {
    if (t.asset_state === 'OFFLINE') return '#64748b';
    if (t.alert_status === 'RESTRICTED_ZONE' || t.alert_status === 'CRITICAL_VITALS') return '#ff4444';
    if (t.alert_status && t.alert_status !== 'NORMAL') return '#ffb300';
    return '#22c55e';
  },

  _redraw() {
    if (!this._map || !this._ctx) return;
    this._resizeCanvas();
    const ctx = this._ctx;
    const w = this._map.getSize().x;
    const h = this._map.getSize().y;
    ctx.clearRect(0, 0, w, h);

    if (window.layerState && window.layerState.trackers === false) return;

    const floorIdx = window._currentFloor != null ? window._currentFloor : 0;

    Object.values(this._trackers).forEach(t => {
      if (t.pos_x == null || t.pos_y == null) return;
      if (window._applyFloorFilter && window.HoloCoords && !window.HoloCoords.trackerOnFloor(t, floorIdx)) return;

      const pt = this._map.latLngToContainerPoint(
        typeof window.realToLatLng === 'function'
          ? window.realToLatLng(t.pos_x, t.pos_y)
          : L.latLng(t.pos_y, t.pos_x)
      );
      if (pt.x < -20 || pt.y < -20 || pt.x > w + 20 || pt.y > h + 20) return;

      const color = this._colorForTracker(t);
      const r = t.id === this._selectedId ? this._dotRadius + 3 : this._dotRadius;

      ctx.beginPath();
      ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.strokeStyle = t.id === this._selectedId ? '#ffffff' : 'rgba(0,0,0,0.35)';
      ctx.lineWidth = t.id === this._selectedId ? 2.5 : 1;
      ctx.stroke();

      if (t.id === this._selectedId) {
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, r + 5, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(255,255,255,0.5)';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
    });
  },

  _onClick(e) {
    if (!this._map) return;
    const rect = this._canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    let best = null;
    let bestDist = this._hitRadius;

    Object.values(this._trackers).forEach(t => {
      if (t.pos_x == null || t.pos_y == null) return;
      const pt = this._map.latLngToContainerPoint(
        typeof window.realToLatLng === 'function'
          ? window.realToLatLng(t.pos_x, t.pos_y)
          : L.latLng(t.pos_y, t.pos_x)
      );
      const d = Math.hypot(pt.x - x, pt.y - y);
      if (d < bestDist) {
        bestDist = d;
        best = t;
      }
    });

    if (best && window.selectTracker) window.selectTracker(best.id);
  },
});
