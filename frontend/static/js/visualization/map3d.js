/**
 * HOLO-RTLS — 3D Tunnel View (Three.js)
 */
let map3d = null;
let renderer = null;
let scene = null;
let camera = null;
let animFrame = null;

function initMap3D() {
  const container = document.getElementById('map3d');
  const canvas = document.getElementById('threeCanvas');
  const w = container.clientWidth;
  const h = container.clientHeight;

  // ── Renderer ────────────────────────────────────────────────────────────
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setSize(w, h);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x070b18, 1);

  // ── Scene ──────────────────────────────────────────────────────────────
  scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x070b18, 0.004);

  // ── Camera (Perspective) ────────────────────────────────────────────────
  camera = new THREE.PerspectiveCamera(60, w / h, 0.1, 2000);
  camera.position.set(0, 30, 80);
  camera.lookAt(0, 0, 0);

  // ── Lights ─────────────────────────────────────────────────────────────
  const ambient = new THREE.AmbientLight(0x0a1428, 1.5);
  scene.add(ambient);
  const dirLight = new THREE.DirectionalLight(0x00e5ff, 0.6);
  dirLight.position.set(50, 100, 50);
  scene.add(dirLight);
  const pointLight = new THREE.PointLight(0xe040fb, 0.4, 200);
  pointLight.position.set(-50, 20, -30);
  scene.add(pointLight);

  // ── Grid helper (floor reference) ────────────────────────────────────────
  const gridHelper = new THREE.GridHelper(200, 40, 0x00e5ff, 0x0a1a2a);
  gridHelper.material.opacity = 0.3;
  gridHelper.material.transparent = true;
  scene.add(gridHelper);

  // ── Axis helper ─────────────────────────────────────────────────────────
  const axesHelper = new THREE.AxesHelper(20);
  scene.add(axesHelper);

  // ── Tunnel walls (placeholder box) ──────────────────────────────────────
  const wallMat = new THREE.MeshStandardMaterial({
    color: 0x0a1429, transparent: true, opacity: 0.6,
    side: THREE.BackSide, metalness: 0.3, roughness: 0.8,
  });
  const tunnelGeo = new THREE.BoxGeometry(120, 20, 200);
  const tunnel = new THREE.Mesh(tunnelGeo, wallMat);
  tunnel.position.set(0, 10, 0);
  scene.add(tunnel);

  // ── Wireframe overlay on tunnel ─────────────────────────────────────────
  const wireGeo = new THREE.EdgesGeometry(tunnelGeo);
  const wireMat = new THREE.LineBasicMaterial({ color: 0x00e5ff, opacity: 0.2, transparent: true });
  const wireframe = new THREE.LineSegments(wireGeo, wireMat);
  wireframe.position.copy(tunnel.position);
  scene.add(wireframe);

  // ── Orbit controls (manual) ──────────────────────────────────────────────
  setupOrbitControls();

  // ── Resize handler ───────────────────────────────────────────────────────
  window.addEventListener('resize', () => {
    const w2 = container.clientWidth;
    const h2 = container.clientHeight;
    camera.aspect = w2 / h2;
    camera.updateProjectionMatrix();
    renderer.setSize(w2, h2);
  });

  // ── Render loop ─────────────────────────────────────────────────────────
  animate();

  // ── Render tracker dots ──────────────────────────────────────────────────
  render3DTrackerDots();
}

// ── Orbit Controls (simple manual implementation) ─────────────────────────────
let isDragging = false;
let lastX = 0, lastY = 0;
let camTheta = 0.5;   // Horizontal angle
let camPhi = 0.4;    // Vertical angle
let camDist = 100;

function setupOrbitControls() {
  const c = document.getElementById('map3d');
  c.addEventListener('mousedown', e => { isDragging = true; lastX = e.clientX; lastY = e.clientY; });
  c.addEventListener('mouseup', () => isDragging = false);
  c.addEventListener('mouseleave', () => isDragging = false);
  c.addEventListener('mousemove', e => {
    if (!isDragging) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    camTheta -= dx * 0.005;
    camPhi = Math.max(0.05, Math.min(Math.PI / 2 - 0.05, camPhi - dy * 0.005));
    lastX = e.clientX; lastY = e.clientY;
  });
  c.addEventListener('wheel', e => {
    camDist = Math.max(20, Math.min(300, camDist + e.deltaY * 0.1));
  });
}

function updateCamera() {
  const x = camDist * Math.sin(camPhi) * Math.cos(camTheta);
  const y = camDist * Math.cos(camPhi);
  const z = camDist * Math.sin(camPhi) * Math.sin(camTheta);
  camera.position.set(x, y, z);
  camera.lookAt(0, 0, 0);
}

// ── Render loop ────────────────────────────────────────────────────────────────
function animate() {
  animFrame = requestAnimationFrame(animate);
  updateCamera();
  renderer.render(scene, camera);
}

// ── Tracker dot spheres in 3D ──────────────────────────────────────────────────
let trackerMeshes = {};

function render3DTrackerDots() {
  // Remove old meshes
  Object.values(trackerMeshes).forEach(m => scene.remove(m));
  trackerMeshes = {};

  trackers.forEach(t => {
    if (t.pos_x === undefined || t.pos_y === undefined) return;
    const color = trackerColor(t.alert_status, t.asset_state);
    const geo = new THREE.SphereGeometry(0.5, 8, 8);
    const mat = new THREE.MeshStandardMaterial({
      color, emissive: color, emissiveIntensity: 0.6, metalness: 0.3, roughness: 0.4,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(t.pos_x, t.pos_z || 1, t.pos_y);
    mesh._trackerId = t.id;
    mesh.onClick = () => selectTracker(t.id);

    // Click handler via raycasting
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    scene.add(mesh);
    trackerMeshes[t.id] = mesh;
  });
}

function trackerColor(status, state) {
  if (state === 'OFFLINE') return 0x475569;
  if (status === 'NORMAL') return 0x00e5ff;
  if (status === 'RESTRICTED_ZONE' || status === 'CRITICAL_VITALS') return 0xff4444;
  return 0xffb300;
}
