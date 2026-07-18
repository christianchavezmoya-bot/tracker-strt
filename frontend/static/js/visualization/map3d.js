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

let _camTheta = 0.6;
let _camPhi = 0.45;
let _camDist = 120;
let _isDragging = false;
let _lastX = 0, _lastY = 0;
let _touchDist = 0;
let _touchMid = { x: 0, y: 0 };

function initMap3D() {
  const container = document.getElementById('map3d');
  const canvas = document.getElementById('threeCanvas');

  // ── Renderer ────────────────────────────────────────────────────────────
  window._renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    alpha: true,
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
  window._camera = new THREE.PerspectiveCamera(55, w / h, 0.1, 3000);
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

  // ── Floor plan (3D plane with texture) ────────────────────────────────
  loadFloorPlan3D();

  // ── Grid ───────────────────────────────────────────────────────────────
  const grid = new THREE.GridHelper(400, 80, 0x00e5ff, 0x0a1a2a);
  grid.material.opacity = 0.25;
  grid.material.transparent = true;
  grid.position.y = 0.01;
  window._scene.add(grid);

  // ── Axes ───────────────────────────────────────────────────────────────
  const axes = new THREE.AxesHelper(15);
  axes.position.set(-5, 0.1, -5);
  window._scene.add(axes);

  // ── Orbit controls ─────────────────────────────────────────────────────
  setup3DOrbitControls(canvas);
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    _camDist = Math.max(20, Math.min(400, _camDist + e.deltaY * 0.08));
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

  // ── Animation loop ───────────────────────────────────────────────────
  animate3D();

  // ── Render zones ───────────────────────────────────────────────────────
  render3DZones();

  // ── Render tracker dots ────────────────────────────────────────────────
  window.focus3DTracker = focus3DTracker;
  window.updateTrackerDot3D = updateTrackerDot3D;
  window.render3DTrackerDots = render3DTrackerDots;
  render3DTrackerDots();
}

// ── Floor plan in 3D ──────────────────────────────────────────────────────────
function loadFloorPlan3D() {
  // Try to load the floor plan image as a texture
  const loader = new THREE.TextureLoader();
  const imgUrl = '/static/assets/floor-plan-placeholder.png';

  loader.load(imgUrl,
    texture => {
      _floorTexture = texture;
      texture.wrapS = THREE.ClampToEdgeWrapping;
      texture.wrapT = THREE.ClampToEdgeWrapping;

      // The mining map image dimensions: ~1200x3500px (tall portrait)
      const imgAspect = texture.image.naturalWidth / texture.image.naturalHeight;
      const planeW = 200;  // real-world width in meters
      const planeH = planeW / imgAspect;

      const geo = new THREE.PlaneGeometry(planeW, planeH);
      const mat = new THREE.MeshStandardMaterial({
        map: texture,
        transparent: true,
        opacity: 0.85,
        roughness: 0.9,
        metalness: 0.0,
        side: THREE.DoubleSide,
      });
      window._floorMesh = new THREE.Mesh(geo, mat);
      window._floorMesh.rotation.x = -Math.PI / 2;
      window._floorMesh.position.y = 0;
      window._floorMesh.receiveShadow = true;
      window._scene.add(window._floorMesh);

      // Grid scale
      const grid = window._scene.children.find(c => c.isGridHelper);
      if (grid) {
        grid.dispose();
        const idx = window._scene.children.indexOf(grid);
        window._scene.children.splice(idx, 1);
      }
    },
    undefined,
    () => {
      // No floor plan image — use a dark plane as fallback
      const geo = new THREE.PlaneGeometry(200, 200);
      const mat = new THREE.MeshStandardMaterial({
        color: 0x0a1429, roughness: 1.0, metalness: 0.0,
      });
      window._floorMesh = new THREE.Mesh(geo, mat);
      window._floorMesh.rotation.x = -Math.PI / 2;
      window._scene.add(window._floorMesh);
    }
  );
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
      const height = 0.3;  // Thin ring

      // Cylinder ring
      const geo = new THREE.CylinderGeometry(radius, radius, height, 32, 1, true);
      const mat = new THREE.MeshStandardMaterial({
        color, transparent: true, opacity: 0.3,
        side: THREE.DoubleSide, wireframe: zone.zone_type !== 'RESTRICTED',
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(zone.pos_x, height / 2, zone.pos_y);
      window._scene.add(mesh);
      window._zoneMeshes[zone.id] = mesh;
    });
  } catch {}
}

// ── 3D Tracker dots ──────────────────────────────────────────────────────────
function render3DTrackerDots() {
  // Remove old meshes
  Object.values(window._trackerMeshes).forEach(m => window._scene.remove(m));
  window._trackerMeshes = {};

  Object.values(window.trackers || {}).forEach(t => {
    if (t.pos_x === undefined || t.pos_y === undefined) return;
    add3DTrackerDot(t);
  });
}

function add3DTrackerDot(t) {
  const color = colorForTracker(t);
  const geo = new THREE.SphereGeometry(0.6, 10, 10);
  const mat = new THREE.MeshStandardMaterial({
    color,
    emissive: color,
    emissiveIntensity: 0.5,
    roughness: 0.3,
    metalness: 0.4,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.position.set(t.pos_x, t.pos_z || 1, t.pos_y);
  mesh._trackerId = t.id;
  mesh.castShadow = true;

  // Glow ring
  const ringGeo = new THREE.RingGeometry(0.7, 1.0, 24);
  const ringMat = new THREE.MeshBasicMaterial({
    color, transparent: true, opacity: 0.3, side: THREE.DoubleSide,
  });
  const ring = new THREE.Mesh(ringGeo, ringMat);
  ring.rotation.x = -Math.PI / 2;
  ring.position.set(t.pos_x, 0.02, t.pos_y);
  mesh._ring = ring;

  window._scene.add(mesh);
  window._scene.add(ring);
  window._trackerMeshes[t.id] = mesh;
}

function updateTrackerDot3D(tid, pos) {
  const mesh = window._trackerMeshes[tid];
  if (!mesh) {
    // Add new dot
    if (window.trackers && window.trackers[tid]) {
      add3DTrackerDot({ ...window.trackers[tid], ...pos });
    }
    return;
  }
  mesh.position.set(pos.x, pos.z || 1, pos.y);
  if (mesh._ring) {
    mesh._ring.position.set(pos.x, 0.02, pos.y);
  }
}

function focus3DTracker(tid) {
  const t = window.trackers && window.trackers[tid];
  if (!t || t.pos_x === undefined) return;
  // Animate camera to focus on tracker
  const targetX = t.pos_x;
  const targetY = t.pos_y;
  // Keep current angles, just change distance
  _camDist = Math.min(_camDist, 50);
  // Smooth lerp toward target would be better, for now just update
  updateCamera3D();
}

function colorForTracker(t) {
  if (t.asset_state === 'OFFLINE') return 0x475569;
  if (t.alert_status === 'RESTRICTED_ZONE' || t.alert_status === 'CRITICAL_VITALS') return 0xff4444;
  if (t.alert_status !== 'NORMAL') return 0xffb300;
  return 0x00e5ff;
}

// ── Orbit controls ────────────────────────────────────────────────────────────
function setup3DOrbitControls(canvas) {
  // Mouse
  canvas.addEventListener('mousedown', e => {
    _isDragging = true;
    _lastX = e.clientX;
    _lastY = e.clientY;
    canvas.style.cursor = 'grabbing';
  });
  canvas.addEventListener('mouseup', () => {
    _isDragging = false;
    canvas.style.cursor = 'grab';
  });
  canvas.addEventListener('mouseleave', () => {
    _isDragging = false;
    canvas.style.cursor = 'grab';
  });
  canvas.addEventListener('mousemove', e => {
    if (!_isDragging) return;
    const dx = e.clientX - _lastX;
    const dy = e.clientY - _lastY;
    _camTheta -= dx * 0.005;
    _camPhi = Math.max(0.05, Math.min(Math.PI / 2 - 0.05, _camPhi - dy * 0.005));
    _lastX = e.clientX;
    _lastY = e.clientY;
  });

  // Touch — single finger rotate, two finger pinch zoom
  canvas.addEventListener('touchstart', e => {
    e.preventDefault();
    if (e.touches.length === 1) {
      _isDragging = true;
      _lastX = e.touches[0].clientX;
      _lastY = e.touches[0].clientY;
    } else if (e.touches.length === 2) {
      _isDragging = false;
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
      _camDist = Math.max(20, Math.min(400, _camDist - (newDist - _touchDist) * 0.3));
      _touchDist = newDist;
    }
  }, { passive: false });

  canvas.addEventListener('touchend', () => { _isDragging = false; });

  canvas.style.cursor = 'grab';
}

function updateCamera3D() {
  const x = _camDist * Math.sin(_camPhi) * Math.cos(_camTheta);
  const y = _camDist * Math.cos(_camPhi);
  const z = _camDist * Math.sin(_camPhi) * Math.sin(_camTheta);
  if (window._camera) {
    window._camera.position.set(x, y, z);
    window._camera.lookAt(0, 0, 0);
  }
}

// ── 3D Click to select tracker ──────────────────────────────────────────────
function on3DClick(e) {
  const rect = e.target.getBoundingClientRect();
  const mouse = new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1,
  );
  raycastTracker(mouse);
}

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
  if (!window._camera || !window._scene) return;
  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(mouse, window._camera);
  const dots = Object.values(window._trackerMeshes);
  const hits = raycaster.intersectObjects(dots);
  if (hits.length > 0) {
    const tid = hits[0].object._trackerId;
    if (tid && window.selectTracker) window.selectTracker(tid);
  }
}

// ── Animation loop ────────────────────────────────────────────────────────────
function animate3D() {
  window._animId = requestAnimationFrame(animate3D);
  updateCamera3D();

  // Pulse tracker glow
  const t = Date.now() * 0.002;
  Object.values(window._trackerMeshes).forEach((mesh, i) => {
    const pulse = 0.4 + 0.15 * Math.sin(t + i * 0.8);
    if (mesh.material) mesh.material.emissiveIntensity = pulse;
  });

  window._renderer.render(window._scene, window._camera);
}
