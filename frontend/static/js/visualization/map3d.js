/**
 * HOLO-RTLS — 3D Map View (Three.js)
 *
 * Features:
 * - Floor plan image as 3D texture on ground plane
 * - Tag dots as glowing 3D spheres
 * - Zone rings as 3D torus/cylinder geometry
 * - Section polygons as extruded 3D shapes
 * - Orbit camera with mouse + touch support
 * - Real-time dot positions via SSE (updateTrackerDot)
 */
window._scene = null;
window._camera = null;
window._renderer = null;
window._animId = null;
window._floorMesh = null;
window._trackerMeshes = {};
window._zoneMeshes = {};
window._sectionMeshes = {};
window._floorTexture = null;
window._trailLines = {};
window._trailBuffers = {};
window._selectedTrackerId = null;
window._selectedTrackerRing = null;
window._currentFloor = 0;
window._applyFloorFilter = false;
window._applyFloorFilter3D = false;

const MAX_INSTANCED_TRACKERS = 512;
/** Match Leaflet mine map zoom range (map2d.js). */
const MAP2D_MIN_ZOOM = -2;
const MAP2D_MAX_ZOOM = 22;
const MAP2D_FIT_MAX_ZOOM = 18;
const MAP2D_FOCUS_ZOOM = 17;
const CAM_FOV_DEG = 55;

let _trackerInstanced = null;
let _trackerIdToIndex = new Map();
let _indexToTrackerId = [];
let _needsRender3D = true;
let _nodeMeshes3D = {};
let _dummy = new THREE.Object3D();

let _camTheta = 0.6;
let _camPhi = 0.45;
let _camDist = 120;
let _camTargetX = 12.5;
let _camTargetZ = 25;
let _floorLoadGen = 0;
let _loadedFloorUrl = null;
let _floorPlanOpacity = 0.85;
let _isDragging = false;
let _isPanning = false;
let _lastX = 0, _lastY = 0;
let _touchDist = 0;
let _touchMid = { x: 0, y: 0 };

function _cameraHFovRad() {
  const aspect = window._camera?.aspect || 1.33;
  const vFov = CAM_FOV_DEG * Math.PI / 180;
  return 2 * Math.atan(Math.tan(vFov / 2) * aspect);
}

function _viewportSize() {
  const el = document.getElementById('map3d') || document.getElementById('map2d');
  return { w: el?.clientWidth || 800, h: el?.clientHeight || 600 };
}

/** Convert 2D Leaflet zoom level to equivalent orbit camera distance. */
function camDistForZoom2D(zoom) {
  const { w, h } = _viewportSize();
  const z = Math.max(MAP2D_MIN_ZOOM, Math.min(MAP2D_MAX_ZOOM, zoom));
  const scale = Math.pow(2, z);
  const visibleSpan = Math.min(w, h) / scale;
  const hFov = _cameraHFovRad();
  const pitchFactor = Math.max(0.15, Math.sin(_camPhi));
  return (visibleSpan / 2) / (Math.tan(hFov / 2) * pitchFactor);
}

/** Inverse: current camera distance → equivalent 2D zoom. */
function zoom2DForCamDist(dist) {
  const { w, h } = _viewportSize();
  const hFov = _cameraHFovRad();
  const pitchFactor = Math.max(0.15, Math.sin(_camPhi));
  const visibleSpan = 2 * dist * Math.tan(hFov / 2) * pitchFactor;
  const scale = Math.min(w, h) / Math.max(visibleSpan, 1e-6);
  return Math.max(MAP2D_MIN_ZOOM, Math.min(MAP2D_MAX_ZOOM, Math.log2(scale)));
}

function clampCamDist(dist) {
  const minD = camDistForZoom2D(MAP2D_MAX_ZOOM);
  const maxD = camDistForZoom2D(MAP2D_MIN_ZOOM);
  return Math.max(Math.max(minD, 0.5), Math.min(maxD, dist));
}

function fitZoom2DForFloor(extents) {
  const { w, h } = _viewportSize();
  const pad = 0.03;
  const zx = Math.log2(w * (1 - pad) / Math.max(extents.widthM, 1));
  const zy = Math.log2(h * (1 - pad) / Math.max(extents.heightM, 1));
  return Math.max(MAP2D_MIN_ZOOM, Math.min(MAP2D_FIT_MAX_ZOOM, Math.min(zx, zy)));
}

function alignFloorTextureTo2D(texture) {
  if (!texture) return;
  // Leaflet imageOverlay bounds [[maxY,minX],[minY,maxX]] map image top → +Y (world Z).
  texture.flipY = false;
  texture.wrapS = THREE.ClampToEdgeWrapping;
  texture.wrapT = THREE.ClampToEdgeWrapping;
  texture.repeat.y = -1;
  texture.offset.y = 1;
  texture.needsUpdate = true;
}

function zoom3DByWheelDelta(deltaY) {
  const step = deltaY > 0 ? -1 : 1;
  _camDist = clampCamDist(camDistForZoom2D(zoom2DForCamDist(_camDist) + step));
}

function panCamera3D(dx, dy) {
  const panScale = _camDist * 0.0015;
  const sinT = Math.sin(_camTheta);
  const cosT = Math.cos(_camTheta);
  _camTargetX -= (dx * cosT - dy * sinT) * panScale;
  _camTargetZ -= (dx * sinT + dy * cosT) * panScale;
}

/** Mine grid metres → 3D world X/Z (aligned with 2D floor plan bounds). */
function mineToWorldXZ(rx, ry) {
  if (window.HoloCoords && window.HoloCoords.realToDisplay) {
    const d = window.HoloCoords.realToDisplay(rx, ry);
    return { x: d.mapX, z: d.mapY };
  }
  return { x: rx, z: ry };
}

function initMap3D() {
  const container = document.getElementById('map3d');
  const canvas = document.getElementById('threeCanvas');
  if (!container || !canvas) {
    throw new Error('3D map container not found');
  }
  if (typeof THREE === 'undefined') {
    throw new Error('Three.js not loaded');
  }

  // ── Renderer ────────────────────────────────────────────────────────────
  window._renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    alpha: true,
    failIfMajorPerformanceCaveat: false,
  });
  const w = container.clientWidth || 800;
  const h = container.clientHeight || 600;
  window._renderer.setSize(w, h);
  window._renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  window._renderer.setClearColor(0x070b18, 1);
  window._renderer.shadowMap.enabled = true;
  window._renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  // ── Scene ──────────────────────────────────────────────────────────────
  window._scene = new THREE.Scene();
  window._scene.fog = new THREE.FogExp2(0x070b18, 0.003);

  // ── Camera ─────────────────────────────────────────────────────────────
  window._camera = new THREE.PerspectiveCamera(CAM_FOV_DEG, w / h, 0.01, 3000);
  updateCamera3D();

  // ── Lights ──────────────────────────────────────────────────────────────
  const ambient = new THREE.AmbientLight(0x0a1a3a, 2.0);
  window._scene.add(ambient);

  const dirLight = new THREE.DirectionalLight(0x00e5ff, 0.8);
  dirLight.position.set(100, 200, 80);
  dirLight.castShadow = true;
  window._scene.add(dirLight);

  const fillLight = new THREE.DirectionalLight(0xe040fb, 0.3);
  fillLight.position.set(-80, 40, -60);
  window._scene.add(fillLight);

  // ── Floor plan (loaded on init + each 3D view switch) ─────────────────
  // Grid sized to floor after first load — placeholder until then
  window._gridHelper = null;

  // ── Axes ───────────────────────────────────────────────────────────────
  const axes = new THREE.AxesHelper(15);
  axes.position.set(-5, 0.1, -5);
  window._scene.add(axes);

  // ── Instanced tracker dots ─────────────────────────────────────────────
  initTrackerInstancing();

  // ── Orbit controls ─────────────────────────────────────────────────────
  setup3DOrbitControls(canvas);
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    zoom3DByWheelDelta(e.deltaY);
    mark3DDirty();
  }, { passive: false });

  // ── Click / touch for tracker selection ────────────────────────────────
  canvas.addEventListener('click', on3DClick);
  canvas.addEventListener('touchend', on3DTouchEnd, { passive: true });

  // ── Resize ─────────────────────────────────────────────────────────────
  const ro = new ResizeObserver(() => {
    const w2 = container.clientWidth;
    const h2 = container.clientHeight;
    window._camera.aspect = w2 / h2;
    window._camera.updateProjectionMatrix();
    window._renderer.setSize(w2, h2);
  });
  ro.observe(container);

  // ── Animation loop (render-on-demand) ────────────────────────────────
  window.mark3DDirty = mark3DDirty;
  animate3D();

  // ── Render zones & anchors ───────────────────────────────────────────
  render3DZones();
  render3DNodes();

  // ── Render tracker dots ────────────────────────────────────────────────
  window.focus3DTracker = focus3DTracker;
  window.updateTrackerDot3D = updateTrackerDot3D;
  window.render3DTrackerDots = render3DTrackerDots;
  render3DTrackerDots();

  window.reloadFloorPlan3D = reloadFloorPlan3D;
  window.fit3DCameraToFloor = fit3DCameraToFloor;
  window.setFloorPlanOpacity3D = setFloorPlanOpacity3D;
  window.sync3DCameraFrom2D = sync3DCameraFrom2D;
  window.sync2DViewFrom3D = sync2DViewFrom3D;
  window.camDistForZoom2D = camDistForZoom2D;
  window.zoom2DForCamDist = zoom2DForCamDist;
  window.zoom3DByWheelDelta = zoom3DByWheelDelta;
  window.get3DCameraState = () => ({
    targetX: _camTargetX,
    targetZ: _camTargetZ,
    dist: _camDist,
    theta: _camTheta,
    phi: _camPhi,
  });
}

function mark3DDirty() {
  _needsRender3D = true;
}

function initTrackerInstancing() {
  const geo = new THREE.SphereGeometry(0.55, 8, 8);
  const mat = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    emissive: 0x111111,
    emissiveIntensity: 0.4,
    roughness: 0.35,
    metalness: 0.35,
  });
  _trackerInstanced = new THREE.InstancedMesh(geo, mat, MAX_INSTANCED_TRACKERS);
  _trackerInstanced.count = 0;
  _trackerInstanced.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  window._scene.add(_trackerInstanced);
  window._trackerMeshes = {};
}

function _hexToThreeColor(hex) {
  return new THREE.Color(hex);
}

function _syncInstancedTrackers() {
  if (!_trackerInstanced) return;
  if (window.layerState && window.layerState.trackers === false) {
    _trackerInstanced.count = 0;
    _trackerInstanced.instanceMatrix.needsUpdate = true;
    mark3DDirty();
    return;
  }

  _trackerIdToIndex.clear();
  _indexToTrackerId = [];
  let i = 0;
  const floorIdx = window._currentFloor != null ? window._currentFloor : 0;

  Object.values(window.trackers || {}).forEach(t => {
    if (t.pos_x == null || t.pos_y == null) return;
    if (window._applyFloorFilter3D && window.HoloCoords && !window.HoloCoords.trackerOnFloor(t, floorIdx)) return;
    if (i >= MAX_INSTANCED_TRACKERS) return;

    _trackerIdToIndex.set(t.id, i);
    _indexToTrackerId[i] = t.id;
    const w = mineToWorldXZ(t.pos_x, t.pos_y);
    _dummy.position.set(w.x, t.pos_z != null ? t.pos_z : 1, w.z);
    _dummy.updateMatrix();
    _trackerInstanced.setMatrixAt(i, _dummy.matrix);
    _trackerInstanced.setColorAt(i, _hexToThreeColor(colorForTracker(t)));
    i++;
  });

  _trackerInstanced.count = i;
  _trackerInstanced.instanceMatrix.needsUpdate = true;
  if (_trackerInstanced.instanceColor) _trackerInstanced.instanceColor.needsUpdate = true;
  mark3DDirty();
}

function setFloorPlanOpacity3D(opacity) {
  const op = Math.max(0.1, Math.min(1, parseFloat(opacity) || 0.85));
  _floorPlanOpacity = op;
  if (window._floorMesh && window._floorMesh.material) {
    window._floorMesh.material.transparent = op < 1 || !!window._floorMesh.material.map;
    window._floorMesh.material.opacity = op;
    window._floorMesh.material.needsUpdate = true;
    mark3DDirty();
  }
}

function getFloorExtents3D() {
  if (window.HoloCoords) {
    return window.HoloCoords.getFloorExtents();
  }
  return { widthM: 50, heightM: 50, minX: 0, minY: 0, maxX: 50, maxY: 50 };
}

function fit3DCameraToFloor(extents) {
  const e = extents || getFloorExtents3D();
  _camTargetX = e.minX + e.widthM / 2;
  _camTargetZ = e.minY + e.heightM / 2;
  _camDist = clampCamDist(camDistForZoom2D(fitZoom2DForFloor(e)));
  updateCamera3D();
  mark3DDirty();
}

function sync3DCameraFrom2D() {
  if (!window._map2d) return;
  const map = window._map2d;
  const center = map.getCenter();
  _camTargetX = center.lng;
  _camTargetZ = center.lat;
  _camDist = clampCamDist(camDistForZoom2D(map.getZoom()));
  updateCamera3D();
  mark3DDirty();
}

function sync2DViewFrom3D() {
  if (!window._map2d) return;
  const zoom = Math.round(zoom2DForCamDist(_camDist) * 10) / 10;
  window._map2d.setView(
    L.latLng(_camTargetZ, _camTargetX),
    Math.max(MAP2D_MIN_ZOOM, Math.min(MAP2D_MAX_ZOOM, zoom)),
    { animate: false }
  );
  if (window.renderTrackerDots) window.renderTrackerDots();
}

function updateGridForFloor(extents) {
  if (!window._scene) return;
  const e = extents || getFloorExtents3D();
  _camTargetX = e.minX + e.widthM / 2;
  _camTargetZ = e.minY + e.heightM / 2;
  if (window._gridHelper) {
    window._scene.remove(window._gridHelper);
    window._gridHelper.geometry.dispose();
    window._gridHelper.material.dispose();
    window._gridHelper = null;
  }
  const span = Math.max(e.widthM, e.heightM, 10);
  const size = span * 1.08;
  const divisions = Math.min(60, Math.max(6, Math.round(span / 2)));
  const grid = new THREE.GridHelper(size, divisions, 0x00e5ff, 0x0a1a2a);
  grid.material.opacity = 0.25;
  grid.material.transparent = true;
  grid.position.set(_camTargetX, 0.01, _camTargetZ);
  window._scene.add(grid);
  window._gridHelper = grid;
  mark3DDirty();
}

async function verifyFloorPlanUrl3D(url) {
  if (!url) return null;
  return new Promise(resolve => {
    const img = new Image();
    img.onload = () => resolve(url);
    img.onerror = () => resolve(null);
    img.src = url + (url.includes('?') ? "&" : "?") + "t=" + Date.now();
  });
}

async function fetchFloorPlanUrlFromApi() {
  try {
    const res = await API.get('/zones/sections');
    const data = await API.json(res);
    const items = (res && res.ok && data.items) ? data.items : [];
    for (const item of items) {
      const url = item && item.image_url;
      if (!url || url.includes('placeholder')) continue;
      const verified = await verifyFloorPlanUrl3D(url);
      if (verified) return verified;
    }
  } catch (_) { /* ignore */ }
  return null;
}

async function resolveFloorPlanUrl3D() {
  const holoUrl = window.HoloCoords ? window.HoloCoords.getFloorPlanUrl() : null;
  if (holoUrl && !holoUrl.includes('placeholder')) {
    const verified = await verifyFloorPlanUrl3D(holoUrl);
    if (verified) return verified;
  }
  const apiUrl = await fetchFloorPlanUrlFromApi();
  if (apiUrl) return apiUrl;
  return '/static/assets/floor-plan-placeholder.png';
}

function applyFloorPlaneMesh(texture, extents, imgUrl) {
  if (!window._scene) return;
  const planeW = Math.max(1, extents.widthM || 50);
  const planeH = Math.max(1, extents.heightM || 50);
  const cx = extents.minX + planeW / 2;
  const cz = extents.minY + planeH / 2;

  if (window._floorMesh) {
    window._scene.remove(window._floorMesh);
    window._floorMesh.geometry.dispose();
    if (window._floorMesh.material.map && window._floorMesh.material.map !== texture) {
      window._floorMesh.material.map.dispose();
    }
    window._floorMesh.material.dispose();
    window._floorMesh = null;
  }

  const geo = new THREE.PlaneGeometry(planeW, planeH);
  const matOpts = {
    roughness: 0.9,
    metalness: 0.0,
    side: THREE.DoubleSide,
  };
  if (texture) {
    matOpts.map = texture;
    matOpts.transparent = true;
    matOpts.opacity = window.getFloorPlanOpacity ? window.getFloorPlanOpacity() : _floorPlanOpacity;
  } else {
    matOpts.color = 0x0a1429;
  }
  const mat = new THREE.MeshStandardMaterial(matOpts);
  window._floorMesh = new THREE.Mesh(geo, mat);
  window._floorMesh.rotation.x = -Math.PI / 2;
  window._floorMesh.position.set(cx, 0, cz);
  window._floorMesh.receiveShadow = true;
  window._scene.add(window._floorMesh);

  _loadedFloorUrl = imgUrl;
  updateGridForFloor(extents);
  fit3DCameraToFloor(extents);
  mark3DDirty();
}

async function loadFloorPlan3D() {
  if (!window._scene) return;
  const loadGen = ++_floorLoadGen;
  const imgUrl = await resolveFloorPlanUrl3D();
  if (loadGen !== _floorLoadGen) return;

  const extents = getFloorExtents3D();
  const loader = new THREE.TextureLoader();
  if (loader.setCrossOrigin) loader.setCrossOrigin('anonymous');

  loader.load(
    imgUrl,
    texture => {
      if (loadGen !== _floorLoadGen) {
        texture.dispose();
        return;
      }
      window._floorTexture = texture;
      alignFloorTextureTo2D(texture);
      applyFloorPlaneMesh(texture, extents, imgUrl);
    },
    undefined,
    () => {
      if (loadGen !== _floorLoadGen) return;
      console.warn('[map3d] Floor plan texture failed to load:', imgUrl);
      if (window.showToast) {
        window.showToast('3D floor plan image failed to load — showing grid only', 'warning');
      }
      applyFloorPlaneMesh(null, extents, imgUrl);
    }
  );
}

async function reloadFloorPlan3D() {
  if (!window._scene) return;
  const url = await resolveFloorPlanUrl3D();
  if (url === _loadedFloorUrl && window._floorMesh && window._floorMesh.material.map) {
    fit3DCameraToFloor();
    mark3DDirty();
    return;
  }
  await loadFloorPlan3D();
}

// ── 3D Zones ──────────────────────────────────────────────────────────────────
async function render3DZones() {
  try {
    const res = await API.get('/zones');
    const data = await API.json(res);
    if (!res || !res.ok || !data.items) return;

    data.items.forEach(zone => {
      if (zone.pos_x === undefined || zone.pos_y === undefined) return;

      const colorMap = {
        RESTRICTED: 0xff4444,
        DANGER: 0xff6b35,
        CHECK_IN: 0x00e5ff,
        CHECK_OUT: 0x00e5ff,
        NORMAL: 0x00e5ff,
      };
      const color = colorMap[zone.zone_type] || 0x00e5ff;
      const radius = zone.radius || 5;
      const zoneHeight = 8;  // 3D box height
      const zoneZ = zone.pos_z || 0;  // Zone height from zone.position.z

      // 3D Box geometry for zone visualization
      const geo = new THREE.BoxGeometry(radius * 2, zoneHeight, radius * 2);
      const mat = new THREE.MeshStandardMaterial({
        color,
        transparent: true,
        opacity: 0.15,
        side: THREE.DoubleSide,
      });
      const mesh = new THREE.Mesh(geo, mat);
      const w = mineToWorldXZ(zone.pos_x, zone.pos_y);
      mesh.position.set(w.x, zoneZ + zoneHeight / 2, w.z);
      mesh._zoneZ = zoneZ;
      mesh._zoneHeight = zoneHeight;
      window._scene.add(mesh);

      // Wireframe overlay for visibility
      const wireGeo = new THREE.BoxGeometry(radius * 2, zoneHeight, radius * 2);
      const wireMat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.4,
        wireframe: true,
      });
      const wireMesh = new THREE.Mesh(wireGeo, wireMat);
      wireMesh.position.copy(mesh.position);
      window._scene.add(wireMesh);

      // Store both meshes for floor visibility toggling
      window._zoneMeshes[zone.id] = { mesh, wireMesh, zoneZ, zoneHeight };
    });
  } catch {}
}

// ── 3D Anchor / node markers ──────────────────────────────────────────────────
async function render3DNodes() {
  try {
    const res = await API.get('/nodes');
    const data = await API.json(res);
    if (!res || !res.ok || !data.items) return;

    Object.values(_nodeMeshes3D).forEach(m => {
      window._scene.remove(m);
      m.geometry.dispose();
      m.material.dispose();
    });
    _nodeMeshes3D = {};

    data.items.forEach(node => {
      if (window.HoloCoords && !window.HoloCoords.isNodePlaced(node)) return;
      const floorIdx = window._currentFloor != null ? window._currentFloor : 0;
      if (window._applyFloorFilter3D && window.HoloCoords && !window.HoloCoords.nodeOnFloor(node, floorIdx)) return;
      const rx = node.pos_x ?? node.position?.x;
      const ry = node.pos_y ?? node.position?.y;
      const rz = Number(node.pos_z ?? node.position?.z ?? 0);
      if (rx == null || ry == null) return;
      const w = mineToWorldXZ(Number(rx), Number(ry));
      const height = Math.max(0.5, rz + 1.25);
      const geo = new THREE.CylinderGeometry(0.4, 0.5, 2.5, 8);
      const mat = new THREE.MeshStandardMaterial({
        color: 0x00e5ff,
        emissive: 0x003344,
        emissiveIntensity: 0.6,
        roughness: 0.4,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(w.x, height, w.z);
      mesh._nodeId = node.id;
      mesh.userData.node = node;
      window._scene.add(mesh);
      _nodeMeshes3D[node.id] = mesh;
    });
    mark3DDirty();
  } catch (_) { /* ignore */ }
}

window.render3DNodes = render3DNodes;

// ── 3D Tracker dots (instanced) ───────────────────────────────────────────────
function render3DTrackerDots() {
  _syncInstancedTrackers();
}

function add3DTrackerDot(t) {
  _syncInstancedTrackers();
}

function updateTrackerDot3D(tid, pos) {
  const t = window.trackers && window.trackers[tid];
  if (!t) return;
  t.pos_x = pos.x;
  t.pos_y = pos.y;
  if (pos.z != null) t.pos_z = pos.z;

  const idx = _trackerIdToIndex.get(tid);
  if (idx == null) {
    _syncInstancedTrackers();
    return;
  }

  const w = mineToWorldXZ(pos.x, pos.y);
  _dummy.position.set(w.x, pos.z != null ? pos.z : 1, w.z);
  _dummy.updateMatrix();
  _trackerInstanced.setMatrixAt(idx, _dummy.matrix);
  _trackerInstanced.instanceMatrix.needsUpdate = true;

  if (!window._trailBuffers[tid]) window._trailBuffers[tid] = [];
  window._trailBuffers[tid].push({ x: pos.x, y: pos.y, z: pos.z || 1 });
  if (window._trailBuffers[tid].length > 50) window._trailBuffers[tid].shift();
  if (window._trailBuffers[tid].length >= 2) {
    window.addTrackerTrail(tid, window._trailBuffers[tid]);
  }
  mark3DDirty();
}

/**
 * Add a trail line for a tracker
 * @param {string} trackerId
 * @param {Array<{x,y,z}>} positions
 */
window.addTrackerTrail = function(trackerId, positions) {
  if (!positions || positions.length < 2) return;

  // Remove existing line
  window.clearTrackerTrail(trackerId);

  // Build flat position array for BufferGeometry
  const posArray = [];
  positions.forEach(p => {
    const w = mineToWorldXZ(p.x, p.y);
    posArray.push(w.x, p.z !== undefined ? p.z : 1, w.z);
  });

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(posArray, 3));

  const material = new THREE.LineBasicMaterial({
    color: 0x00e5ff,
    transparent: true,
    opacity: 0.4,
  });

  const line = new THREE.Line(geometry, material);
  window._scene.add(line);
  window._trailLines[trackerId] = line;
};

/**
 * Clear trail line for a tracker
 * @param {string} trackerId
 */
window.clearTrackerTrail = function(trackerId) {
  const line = window._trailLines[trackerId];
  if (line) {
    window._scene.remove(line);
    line.geometry.dispose();
    line.material.dispose();
    delete window._trailLines[trackerId];
  }
};

function focus3DTracker(tid) {
  const t = window.trackers && window.trackers[tid];
  if (!t || t.pos_x === undefined) return;
  const w = mineToWorldXZ(t.pos_x, t.pos_y);
  _camTargetX = w.x;
  _camTargetZ = w.z;
  _camDist = clampCamDist(camDistForZoom2D(MAP2D_FOCUS_ZOOM));
  updateCamera3D();
  mark3DDirty();
}

function colorForTracker(t) {
  if (t.asset_state === 'OFFLINE') return 0x64748b;
  if (t.alert_status === 'RESTRICTED_ZONE' || t.alert_status === 'CRITICAL_VITALS') return 0xff4444;
  if (t.alert_status !== 'NORMAL') return 0xffb300;
  return 0x22c55e;
}

// ── Orbit controls ────────────────────────────────────────────────────────────
function setup3DOrbitControls(canvas) {
  canvas.addEventListener('mousedown', e => {
    if (e.button === 1 || e.shiftKey) {
      _isPanning = true;
      _isDragging = false;
    } else {
      _isDragging = true;
      _isPanning = false;
    }
    _lastX = e.clientX;
    _lastY = e.clientY;
    canvas.style.cursor = _isPanning ? 'move' : 'grabbing';
    e.preventDefault();
  });
  canvas.addEventListener('mouseup', () => {
    _isDragging = false;
    _isPanning = false;
    canvas.style.cursor = 'grab';
  });
  canvas.addEventListener('mouseleave', () => {
    _isDragging = false;
    _isPanning = false;
    canvas.style.cursor = 'grab';
  });
  canvas.addEventListener('mousemove', e => {
    if (!_isDragging && !_isPanning) return;
    const dx = e.clientX - _lastX;
    const dy = e.clientY - _lastY;
    if (_isPanning) {
      panCamera3D(dx, dy);
    } else {
      _camTheta -= dx * 0.005;
      _camPhi = Math.max(0.05, Math.min(Math.PI / 2 - 0.05, _camPhi - dy * 0.005));
    }
    _lastX = e.clientX;
    _lastY = e.clientY;
    mark3DDirty();
  });
  canvas.addEventListener('contextmenu', e => e.preventDefault());

  // Touch — single finger rotate, two finger pinch zoom / pan
  canvas.addEventListener('touchstart', e => {
    e.preventDefault();
    if (e.touches.length === 1) {
      _isDragging = true;
      _isPanning = false;
      _lastX = e.touches[0].clientX;
      _lastY = e.touches[0].clientY;
    } else if (e.touches.length === 2) {
      _isDragging = false;
      _isPanning = true;
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      _touchDist = Math.sqrt(dx * dx + dy * dy);
      _touchMid = {
        x: (e.touches[0].clientX + e.touches[1].clientX) / 2,
        y: (e.touches[0].clientY + e.touches[1].clientY) / 2,
      };
    }
  }, { passive: false });

  canvas.addEventListener('touchmove', e => {
    e.preventDefault();
    if (e.touches.length === 1 && _isDragging) {
      const dx = e.touches[0].clientX - _lastX;
      const dy = e.touches[0].clientY - _lastY;
      _camTheta -= dx * 0.006;
      _camPhi = Math.max(0.05, Math.min(Math.PI / 2 - 0.05, _camPhi - dy * 0.006));
      _lastX = e.touches[0].clientX;
      _lastY = e.touches[0].clientY;
    } else if (e.touches.length === 2) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      const newDist = Math.sqrt(dx * dx + dy * dy);
      if (_touchDist > 0) {
        const pinchDelta = newDist - _touchDist;
        if (Math.abs(pinchDelta) > 2) {
          zoom3DByWheelDelta(-pinchDelta * 2);
        }
      }
      const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
      const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
      panCamera3D(midX - _touchMid.x, midY - _touchMid.y);
      _touchDist = newDist;
      _touchMid = { x: midX, y: midY };
    }
  }, { passive: false });

  canvas.addEventListener('touchend', () => {
    _isDragging = false;
    _isPanning = false;
  });

  canvas.style.cursor = 'grab';
}

function updateCamera3D() {
  const tx = _camTargetX;
  const tz = _camTargetZ;
  const ox = _camDist * Math.sin(_camPhi) * Math.cos(_camTheta);
  const oy = _camDist * Math.cos(_camPhi);
  const oz = _camDist * Math.sin(_camPhi) * Math.sin(_camTheta);
  if (window._camera) {
    window._camera.position.set(tx + ox, oy, tz + oz);
    window._camera.lookAt(tx, 0, tz);
  }
}

// ── 3D Click to select tracker ──────────────────────────────────────────────
function on3DClick(e) {
  const rect = e.target.getBoundingClientRect();
  const mouse = new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1,
  );
  if (raycastNode(mouse)) return;
  raycastTracker(mouse);
}

function raycastNode(mouse) {
  const meshes = Object.values(_nodeMeshes3D || {});
  if (!meshes.length || !window._camera) return false;
  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(mouse, window._camera);
  const hits = raycaster.intersectObjects(meshes, false);
  if (hits.length > 0 && hits[0].object.userData.node) {
    showNodeEditPanel3D(hits[0].object.userData.node);
    return true;
  }
  return false;
}

function showNodeEditPanel3D(node) {
  let panel = document.getElementById('nodeEdit3DPanel');
  if (!panel) {
    panel = document.createElement('div');
    panel.id = 'nodeEdit3DPanel';
    panel.style.cssText = 'position:absolute;top:72px;right:16px;z-index:30;width:min(300px,90vw);background:rgba(8,15,30,.95);border:1px solid rgba(0,229,255,.35);border-radius:12px;padding:14px;box-shadow:0 8px 32px rgba(0,0,0,.45)';
    document.getElementById('map3d')?.appendChild(panel);
  }
  const rx = node.pos_x ?? node.position?.x ?? 0;
  const ry = node.pos_y ?? node.position?.y ?? 0;
  const rz = node.pos_z ?? node.position?.z ?? 0;
  panel.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
      <div style="font-size:13px;font-weight:700;color:#00e5ff"><i class="fa-solid fa-anchor"></i> Edit anchor</div>
      <button type="button" id="nodeEdit3DClose" style="background:none;border:none;color:#94a3b8;cursor:pointer"><i class="fa-solid fa-xmark"></i></button>
    </div>
    <label style="font-size:11px;color:#94a3b8;display:block;margin-bottom:4px">Name</label>
    <input id="nodeEdit3DName" class="form-input" style="width:100%;margin-bottom:10px;box-sizing:border-box" value="${(node.assigned_name || '').replace(/"/g, '&quot;')}">
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:12px">
      <div><label style="font-size:10px;color:#94a3b8">X (m)</label><input id="nodeEdit3DX" type="number" step="0.1" class="form-input" style="width:100%" value="${Number(rx).toFixed(2)}"></div>
      <div><label style="font-size:10px;color:#94a3b8">Y (m)</label><input id="nodeEdit3DY" type="number" step="0.1" class="form-input" style="width:100%" value="${Number(ry).toFixed(2)}"></div>
      <div><label style="font-size:10px;color:#94a3b8">Z / floor</label><input id="nodeEdit3DZ" type="number" step="0.1" class="form-input" style="width:100%" value="${Number(rz).toFixed(2)}"></div>
    </div>
    <div style="font-size:10px;color:#64748b;margin-bottom:10px;font-family:monospace">${node.mac_address || ''}</div>
    <button type="button" id="nodeEdit3DSave" class="btn btn-primary btn-sm" style="width:100%"><i class="fa-solid fa-floppy-disk"></i> Save</button>`;
  panel.style.display = 'block';
  panel.querySelector('#nodeEdit3DClose').onclick = () => { panel.style.display = 'none'; };
  panel.querySelector('#nodeEdit3DSave').onclick = async () => {
    const body = {
      assigned_name: panel.querySelector('#nodeEdit3DName').value.trim(),
      pos_x: parseFloat(panel.querySelector('#nodeEdit3DX').value) || 0,
      pos_y: parseFloat(panel.querySelector('#nodeEdit3DY').value) || 0,
      pos_z: parseFloat(panel.querySelector('#nodeEdit3DZ').value) || 0,
      metadata: { placed_on_map: true },
    };
    const res = await API.patch('/nodes/' + node.id, body);
    if (res && res.ok) {
      if (window.showToast) window.showToast('Anchor updated', 'success');
      await render3DNodes();
      if (window.renderNodeMarkers) await window.renderNodeMarkers();
      if (window.refreshRtlsSetupUi) window.refreshRtlsSetupUi();
      try { await API.post('/nodes/refresh-positions', {}); } catch (_) {}
      panel.style.display = 'none';
    } else if (window.showToast) window.showToast('Save failed', 'error');
  };
}

window.showNodeEditPanel3D = showNodeEditPanel3D;

function on3DTouchEnd(e) {
  if (e.changedTouches.length === 1) {
    const t = e.changedTouches[0];
    const rect = e.target.getBoundingClientRect();
    const mouse = new THREE.Vector2(
      ((t.clientX - rect.left) / rect.width) * 2 - 1,
      -((t.clientY - rect.top) / rect.height) * 2 + 1,
    );
    raycastTracker(mouse);
  }
}

function raycastTracker(mouse) {
  if (!window._camera || !window._scene || !_trackerInstanced || _trackerInstanced.count === 0) return;
  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(mouse, window._camera);
  const hits = raycaster.intersectObject(_trackerInstanced);
  if (hits.length > 0) {
    const idx = hits[0].instanceId;
    const tid = _indexToTrackerId[idx];
    if (tid && window.selectTracker) window.selectTracker(tid);
    window._selectedTrackerId = tid;
    updateTrackerSelectionVisuals();
  }
}

/**
 * Update visual feedback for selected tracker
 */
function updateTrackerSelectionVisuals() {
  if (window._selectedTrackerRing) {
    window._scene.remove(window._selectedTrackerRing);
    window._selectedTrackerRing.geometry.dispose();
    window._selectedTrackerRing.material.dispose();
    window._selectedTrackerRing = null;
  }

  if (window._selectedTrackerId && _trackerInstanced) {
    const idx = _trackerIdToIndex.get(window._selectedTrackerId);
    if (idx != null) {
      _trackerInstanced.getMatrixAt(idx, _dummy.matrix);
      const pos = new THREE.Vector3();
      pos.setFromMatrixPosition(_dummy.matrix);

      const ringGeo = new THREE.RingGeometry(1.0, 1.4, 32);
      const ringMat = new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.75,
        side: THREE.DoubleSide,
      });
      window._selectedTrackerRing = new THREE.Mesh(ringGeo, ringMat);
      window._selectedTrackerRing.rotation.x = -Math.PI / 2;
      window._selectedTrackerRing.position.set(pos.x, 0.04, pos.z);
      window._scene.add(window._selectedTrackerRing);
    }
  }
  mark3DDirty();
}

/**
 * Set the 3D floor view (0, 1, or 2)
 * @param {number} floorIndex
 */
window.set3DFloor = function(floorIndex) {
  window._currentFloor = floorIndex;
  window._applyFloorFilter = true;
  window._applyFloorFilter3D = true;

  const camPhis = [0.45, 0.35, 0.25];
  _camPhi = camPhis[floorIndex] || 0.45;
  updateCamera3D();

  document.querySelectorAll('.floor-btn').forEach(btn => {
    btn.classList.toggle('active', parseInt(btn.dataset.floor, 10) === floorIndex);
  });

  const threshold = window.HoloCoords ? window.HoloCoords.floorHeightForIndex(floorIndex) : [0, 20, 40][floorIndex];
  Object.values(window._zoneMeshes).forEach(zoneData => {
    const { mesh, wireMesh } = zoneData;
    const show = zoneData.zoneZ <= threshold + 5 && zoneData.zoneZ >= threshold - 5;
    if (mesh) mesh.visible = show;
    if (wireMesh) wireMesh.visible = show;
  });

  Object.values(_nodeMeshes3D || {}).forEach(mesh => {
    const node = mesh.userData && mesh.userData.node;
    if (!node) return;
    const show = !window.HoloCoords || window.HoloCoords.nodeOnFloor(node, floorIndex);
    mesh.visible = show;
  });

  render3DTrackerDots();
  if (window.renderNodeMarkers) window.renderNodeMarkers();
  mark3DDirty();
};

/**
 * Focus camera on the currently selected tracker
 */
window.focusSelectedTracker3D = function() {
  const tid = window._selectedTrackerId || window.selectedTrackerId;
  if (!tid) return;
  focus3DTracker(tid);
};

// ── Animation loop ────────────────────────────────────────────────────────────
function animate3D() {
  window._animId = requestAnimationFrame(animate3D);

  const cameraActive = _isDragging || _isPanning;
  const hasSelectionRing = !!window._selectedTrackerRing;

  if (_needsRender3D || cameraActive || hasSelectionRing) {
    updateCamera3D();

    if (window._selectedTrackerRing && window._selectedTrackerId) {
      const idx = _trackerIdToIndex.get(window._selectedTrackerId);
      if (idx != null && _trackerInstanced) {
        _trackerInstanced.getMatrixAt(idx, _dummy.matrix);
        const pos = new THREE.Vector3();
        pos.setFromMatrixPosition(_dummy.matrix);
        window._selectedTrackerRing.position.set(pos.x, 0.04, pos.z);
      }
      window._selectedTrackerRing.rotation.z += 0.02;
    }

    if (window._renderer && window._scene && window._camera) {
      window._renderer.render(window._scene, window._camera);
    }
    if (!cameraActive && !hasSelectionRing) _needsRender3D = false;
  }
}

// ── Layer visibility toggles (called from dashboard.js) ─────────────────────
window._zoneLayersVisible = true;
window._sectionLayersVisible = true;
window._gridLayersVisible = true;
window._trackerLayersVisible = true;

function toggleZoneLayer3D(show) {
  window._zoneLayersVisible = show;
  Object.values(window._zoneMeshes).forEach(z => {
    if (z && z.mesh) { z.mesh.visible = show; z.wireMesh.visible = show; }
  });
}

function toggleSectionLayer3D(show) {
  window._sectionLayersVisible = show;
  // Sections not rendered in 3D — no-op
}

function toggleGridLayer3D(show) {
  window._gridLayersVisible = show;
  if (window._gridHelper) window._gridHelper.visible = show;
}

function toggleTrackerLayer3D(show) {
  window._trackerLayersVisible = show;
  if (_trackerInstanced) _trackerInstanced.visible = show;
  mark3DDirty();
}

// Global exports
window.toggleZoneLayer3D = toggleZoneLayer3D;
window.toggleSectionLayer3D = toggleSectionLayer3D;
window.toggleGridLayer3D = toggleGridLayer3D;
window.toggleTrackerLayer3D = toggleTrackerLayer3D;

/** Probe whether WebGL is available (GPU or software). */
function isWebGLAvailable() {
  if (typeof THREE === 'undefined') return false;
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl2') || canvas.getContext('webgl')
      || canvas.getContext('experimental-webgl');
    return !!gl;
  } catch {
    return false;
  }
}

/** Lazy-safe 3D init; returns false when WebGL unavailable. */
function ensureMap3D() {
  if (window._map3dReady) return true;
  if (!isWebGLAvailable()) return false;
  initMap3D();
  window._map3dReady = true;
  return true;
}

window.isWebGLAvailable = isWebGLAvailable;
window.ensureMap3D = ensureMap3D;
