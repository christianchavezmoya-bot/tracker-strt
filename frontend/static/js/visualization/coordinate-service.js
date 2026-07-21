/**
 * HOLO-RTLS — Unified coordinate service (ADR-001)
 * Single source for mine metres, floor-plan pixels, and map display helpers.
 */
'use strict';

window.HoloCoords = (function () {
  let _state = {
    calibrated: false,
    imageWidth: 1000,
    imageHeight: 3000,
    affine: { a: 1, b: 0, c: 0, d: 0, e: 1, f: 0 },
    bounds: { minX: 0, maxX: 25, minY: 0, maxY: 50 },
    floorPlanUrl: null,
    floorExtents: { widthM: 200, heightM: 200 },
  };

  function setCalibration(cfg) {
    if (!cfg) return;
    _state.calibrated = !!cfg.calibrated;
    if (cfg.imageWidth) _state.imageWidth = cfg.imageWidth;
    if (cfg.imageHeight) _state.imageHeight = cfg.imageHeight;
    if (cfg.affine) _state.affine = { ...cfg.affine };
    if (cfg.bounds) _state.bounds = { ...cfg.bounds };
    if (cfg.floorPlanUrl) _state.floorPlanUrl = cfg.floorPlanUrl;
    if (cfg.floorExtents) _state.floorExtents = { ...cfg.floorExtents };
  }

  function pixelToReal(px, py) {
    const a = _state.affine;
    return {
      x: a.a * px + a.b * py + a.c,
      y: a.d * px + a.e * py + a.f,
    };
  }

  function realToPixel(rx, ry) {
    if (!_state.calibrated) return { x: rx, y: ry };
    const a = _state.affine;
    const det = a.a * a.e - a.b * a.d;
    if (Math.abs(det) < 1e-10) return { x: rx, y: ry };
    return {
      x: (a.e * (rx - a.c) - a.b * (ry - a.f)) / det,
      y: (-a.d * (rx - a.c) + a.a * (ry - a.f)) / det,
    };
  }

  function getFloorPlanUrl() {
    return _state.floorPlanUrl || '/static/assets/floor-plan-placeholder.png';
  }

  function getFloorExtents() {
    const b = _state.bounds;
    const spanX = Math.max(1, b.maxX - b.minX);
    const spanY = Math.max(1, b.maxY - b.minY);
    return { widthM: spanX, heightM: spanY, minX: b.minX, minY: b.minY, maxX: b.maxX, maxY: b.maxY };
  }

  /**
   * Mine metres → map display coordinates (matches Leaflet imageOverlay bounds).
   * mapX → 2D lng / 3D X; mapY → 2D lat / 3D Z
   */
  function realToDisplay(rx, ry) {
    const px = realToPixel(Number(rx), Number(ry));
    const b = _state.bounds;
    const spanX = Math.max(1, b.maxX - b.minX);
    const spanY = Math.max(1, b.maxY - b.minY);
    const iw = Math.max(1, _state.imageWidth);
    const ih = Math.max(1, _state.imageHeight);
    const mapX = b.minX + (px.x / iw) * spanX;
    const mapY = b.maxY - (px.y / ih) * spanY;
    return { mapX, mapY, x: mapX, y: mapY, z: mapY };
  }

  /** Inverse of realToDisplay for drag / pick on map. */
  function displayToReal(mapX, mapY) {
    const b = _state.bounds;
    const spanX = Math.max(1, b.maxX - b.minX);
    const spanY = Math.max(1, b.maxY - b.minY);
    const iw = Math.max(1, _state.imageWidth);
    const ih = Math.max(1, _state.imageHeight);
    const px = ((mapX - b.minX) / spanX) * iw;
    const py = ((b.maxY - mapY) / spanY) * ih;
    return pixelToReal(px, py);
  }

  function floorHeightForIndex(floorIndex) {
    const heights = [0, 20, 40];
    return heights[floorIndex] ?? 0;
  }

  function trackerOnFloor(tracker, floorIndex) {
    const z = tracker.pos_z != null ? tracker.pos_z : 1;
    const base = floorHeightForIndex(floorIndex);
    return z >= base - 5 && z <= base + 15;
  }

  function nodeOnFloor(node, floorIndex) {
    const z = node.pos_z != null ? node.pos_z : (node.position && node.position.z != null ? node.position.z : 0);
    const base = floorHeightForIndex(floorIndex);
    return z >= base - 5 && z <= base + 15;
  }

  function isNodePlaced(node) {
    const meta = typeof node.metadata === 'object' ? node.metadata : null;
    if (meta && meta.placed_on_map === true) return true;
    if (meta && meta.placed_on_map === false) return false;
    const x = node.position && node.position.x != null ? node.position.x : node.pos_x;
    const y = node.position && node.position.y != null ? node.position.y : node.pos_y;
    return x != null && y != null && (Number(x) !== 0 || Number(y) !== 0);
  }

  return {
    setCalibration,
    pixelToReal,
    realToPixel,
    getFloorPlanUrl,
    getFloorExtents,
    realToDisplay,
    displayToReal,
    floorHeightForIndex,
    trackerOnFloor,
    nodeOnFloor,
    isNodePlaced,
    getState: () => ({ ..._state }),
  };
})();
