/**
 * HOLO-RTLS — Floor Plan Coordinate Setup Wizard
 * Staged GPS georeference flow in Settings → Floor Plans.
 */
'use strict';

const FpCoordWizard = (() => {
  let sectionId = 0;
  let planName = '';
  let imageUrl = '';
  let imageWidth = 1000;
  let imageHeight = 1000;
  let step = 'intro';
  let activePointIndex = 0;
  let points = [{}, {}];
  let onComplete = null;

  let viewZoom = 1;
  let viewPanX = 0;
  let viewPanY = 0;
  let baseFitZoom = 1;
  let isPanning = false;
  let panStart = null;
  let suppressClick = false;

  function el(id) {
    return document.getElementById(id);
  }

  function clamp(v, min, max) {
    return Math.min(max, Math.max(min, v));
  }

  function applyViewTransform() {
    const canvas = el('fpWizardCanvas');
    if (!canvas) return;
    canvas.style.transform = `translate(${viewPanX}px, ${viewPanY}px) scale(${viewZoom})`;
    const label = el('fpWizardZoomLabel');
    if (label) label.textContent = Math.round((viewZoom / baseFitZoom) * 100) + '%';
  }

  function fitViewToImage() {
    const vp = el('fpWizardViewport');
    if (!vp || !imageWidth || !imageHeight) return;
    const vw = vp.clientWidth || 400;
    const vh = vp.clientHeight || 300;
    baseFitZoom = Math.min(vw / imageWidth, vh / imageHeight) * 0.95;
    viewZoom = baseFitZoom;
    viewPanX = (vw - imageWidth * viewZoom) / 2;
    viewPanY = (vh - imageHeight * viewZoom) / 2;
    applyViewTransform();
  }

  function setupImageDimensions() {
    const img = el('fpWizardImage');
    const canvas = el('fpWizardCanvas');
    if (!img || !canvas) return;
    img.style.width = imageWidth + 'px';
    img.style.height = imageHeight + 'px';
    canvas.style.width = imageWidth + 'px';
    canvas.style.height = imageHeight + 'px';
    fitViewToImage();
  }

  /** Viewport client coords → image pixel (accounts for pan/zoom). */
  function clientToImagePixel(clientX, clientY) {
    const vp = el('fpWizardViewport');
    if (!vp) return null;
    const rect = vp.getBoundingClientRect();
    const vx = clientX - rect.left;
    const vy = clientY - rect.top;
    const cx = (vx - viewPanX) / viewZoom;
    const cy = (vy - viewPanY) / viewZoom;
    if (cx < 0 || cy < 0 || cx > imageWidth || cy > imageHeight) return null;
    return { pixel_x: cx, pixel_y: cy };
  }

  function showStep(name) {
    step = name;
    el('fpWizardIntro').style.display = name === 'intro' ? 'block' : 'none';
    el('fpWizardPicker').style.display = (name === 'pick' || name === 'coords') ? 'flex' : 'none';
    el('fpWizardCoordPanel').style.display = name === 'coords' ? 'block' : 'none';
    el('fpWizardConfirmPointBtn').style.display = name === 'pick' ? 'inline-flex' : 'none';
    el('fpWizardMapToolbar').style.display = name === 'pick' ? 'flex' : 'none';
    updatePickerBanner();
    updateConfirmButton();
    if (name === 'pick') {
      requestAnimationFrame(fitViewToImage);
    }
  }

  function updatePickerBanner() {
    const banner = el('fpWizardPickBanner');
    if (!banner || step !== 'pick') return;
    const n = activePointIndex + 1;
    banner.innerHTML =
      `<i class="fa-solid fa-crosshairs"></i> `
      + `Place <strong>point ${n}</strong> on the map — click as many times as you need to adjust. `
      + `Use scroll wheel or <strong>+ / −</strong> to zoom the map only. `
      + `When the marker is correct, click <strong>Enter coordinates</strong>.`;
  }

  function updateConfirmButton() {
    const btn = el('fpWizardConfirmPointBtn');
    if (!btn) return;
    const pt = points[activePointIndex];
    const hasPoint = pt && pt.pixel_x != null;
    btn.disabled = !hasPoint;
    btn.innerHTML = hasPoint
      ? `<i class="fa-solid fa-keyboard"></i> Enter coordinates for point ${activePointIndex + 1}`
      : `<i class="fa-solid fa-crosshairs"></i> Click the map to place point ${activePointIndex + 1}`;
  }

  function renderMarkers() {
    const layer = el('fpWizardMarkers');
    if (!layer) return;
    layer.innerHTML = '';
    points.forEach((pt, i) => {
      if (pt.pixel_x == null) return;
      const dot = document.createElement('div');
      dot.className = 'fp-wizard-marker' + (i === activePointIndex ? ' active' : '');
      dot.style.left = pt.pixel_x + 'px';
      dot.style.top = pt.pixel_y + 'px';
      dot.innerHTML = `<span>${i + 1}</span>`;
      layer.appendChild(dot);
    });
  }

  function openCoordPanel(pointIndex) {
    showStep('coords');
    el('fpWizardCoordTitle').textContent = `Point ${pointIndex + 1} coordinates`;
    el('fpWizardCoordHelp').textContent = pointIndex === 0
      ? 'Enter the latitude and longitude printed on your drawing for this corner.'
      : 'Enter the latitude and longitude for the second corner, then save.';
    el('fpWizardLat').value = points[pointIndex].lat ?? '';
    el('fpWizardLng').value = points[pointIndex].lng ?? '';
    el('fpWizardCoordPanel').dataset.pointIndex = String(pointIndex);
    el('fpWizardSaveBtn').style.display = pointIndex === 1 ? 'inline-flex' : 'none';
    el('fpWizardNextBtn').style.display = pointIndex === 0 ? 'inline-flex' : 'none';
    syncCoordButtons();
  }

  function syncCoordButtons() {
    const lat = el('fpWizardLat');
    const lng = el('fpWizardLng');
    const ok = lat.value.trim() && lng.value.trim();
    el('fpWizardNextBtn').disabled = !ok;
    el('fpWizardSaveBtn').disabled = !ok;
  }

  function bindCoordInputs() {
    el('fpWizardLat').oninput = syncCoordButtons;
    el('fpWizardLng').oninput = syncCoordButtons;
  }

  function handleMapClick(e) {
    if (step !== 'pick' || isPanning || suppressClick) {
      suppressClick = false;
      return;
    }
    e.preventDefault();
    e.stopPropagation();
    const px = clientToImagePixel(e.clientX, e.clientY);
    if (!px) return;
    points[activePointIndex] = { ...points[activePointIndex], pixel_x: px.pixel_x, pixel_y: px.pixel_y };
    renderMarkers();
    updateConfirmButton();
  }

  function handleCrosshairMove(e) {
    const overlay = el('fpWizardCrosshair');
    const vp = el('fpWizardViewport');
    if (!overlay || !vp || step !== 'pick') {
      if (overlay) overlay.style.display = 'none';
      return;
    }
    const rect = vp.getBoundingClientRect();
    if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) {
      overlay.style.display = 'none';
      return;
    }
    overlay.style.display = 'block';
    overlay.style.left = (e.clientX - rect.left) + 'px';
    overlay.style.top = (e.clientY - rect.top) + 'px';
  }

  function zoomAt(factor, clientX, clientY) {
    const vp = el('fpWizardViewport');
    if (!vp) return;
    const rect = vp.getBoundingClientRect();
    const mx = clientX != null ? clientX - rect.left : rect.width / 2;
    const my = clientY != null ? clientY - rect.top : rect.height / 2;
    const newZoom = clamp(viewZoom * factor, baseFitZoom * 0.35, baseFitZoom * 10);
    viewPanX = mx - (mx - viewPanX) * (newZoom / viewZoom);
    viewPanY = my - (my - viewPanY) * (newZoom / viewZoom);
    viewZoom = newZoom;
    applyViewTransform();
  }

  function onWheel(e) {
    if (step !== 'pick') return;
    e.preventDefault();
    e.stopPropagation();
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    zoomAt(factor, e.clientX, e.clientY);
  }

  function onPointerDown(e) {
    if (step !== 'pick') return;
    if (e.button === 1 || e.shiftKey) {
      isPanning = true;
      suppressClick = false;
      panStart = { x: e.clientX, y: e.clientY, panX: viewPanX, panY: viewPanY };
      el('fpWizardViewport').setPointerCapture(e.pointerId);
      e.preventDefault();
    }
  }

  function onPointerMove(e) {
    if (!isPanning || !panStart) return;
    if (Math.abs(e.clientX - panStart.x) > 4 || Math.abs(e.clientY - panStart.y) > 4) {
      suppressClick = true;
    }
    viewPanX = panStart.panX + (e.clientX - panStart.x);
    viewPanY = panStart.panY + (e.clientY - panStart.y);
    applyViewTransform();
    e.preventDefault();
  }

  function onPointerUp(e) {
    if (!isPanning) return;
    isPanning = false;
    panStart = null;
    try { el('fpWizardViewport').releasePointerCapture(e.pointerId); } catch (_) { /* ignore */ }
  }

  function resetViewState() {
    viewZoom = 1;
    viewPanX = 0;
    viewPanY = 0;
    baseFitZoom = 1;
    isPanning = false;
    panStart = null;
    suppressClick = false;
  }

  async function saveGeoref() {
    const idx = parseInt(el('fpWizardCoordPanel').dataset.pointIndex || '1', 10);
    points[idx].lat = parseFloat(el('fpWizardLat').value);
    points[idx].lng = parseFloat(el('fpWizardLng').value);
    if (points.some(p => p.pixel_x == null || p.lat == null || p.lng == null)) {
      if (window.showToast) showToast('Both points with coordinates are required', 'error');
      return;
    }
    const btn = el('fpWizardSaveBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Saving…';
    try {
      const res = await API.post('/positioning/calibration', {
        section_id: sectionId,
        georef_points: points.map(p => ({
          pixel_x: p.pixel_x,
          pixel_y: p.pixel_y,
          lat: p.lat,
          lng: p.lng,
        })),
      });
      const data = await API.json(res);
      if (!res || !res.ok) throw new Error((data && data.error) || 'Save failed');
      if (window.showToast) showToast('Map coordinates saved', 'success');
      close();
      if (typeof onComplete === 'function') onComplete(sectionId, data);
    } catch (err) {
      if (window.showToast) showToast(err.message || 'Failed to save coordinates', 'error');
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-check"></i> Save coordinates';
    }
  }

  function resetState() {
    sectionId = 0;
    planName = '';
    imageUrl = '';
    imageWidth = 1000;
    imageHeight = 1000;
    step = 'intro';
    activePointIndex = 0;
    points = [{}, {}];
    onComplete = null;
    resetViewState();
  }

  function close() {
    el('fpCoordWizardModal').style.display = 'none';
    document.body.style.overflow = '';
    resetState();
  }

  async function open(floorPlan, options = {}) {
    if (!floorPlan || !floorPlan.image_url) {
      if (window.showToast) showToast('Floor plan has no image', 'error');
      return;
    }
    resetState();
    sectionId = floorPlan.id || 0;
    planName = floorPlan.name || 'Floor plan';
    imageUrl = floorPlan.image_url;
    onComplete = options.onComplete || null;

    el('fpWizardPlanName').textContent = planName;
    el('fpCoordWizardModal').style.display = 'flex';
    document.body.style.overflow = 'hidden';

    showStep('intro');

    await new Promise((resolve) => {
      const img = el('fpWizardImage');
      img.onload = () => {
        imageWidth = img.naturalWidth || 1000;
        imageHeight = img.naturalHeight || 1000;
        setupImageDimensions();
        resolve();
      };
      img.onerror = () => resolve();
      img.src = imageUrl;
    });

    if (options.existingPoints && options.existingPoints.length >= 2) {
      points = options.existingPoints.slice(0, 2).map(p => ({ ...p }));
    }
  }

  function init() {
    bindCoordInputs();

    el('fpWizardStartBtn').onclick = () => {
      activePointIndex = 0;
      showStep('pick');
      renderMarkers();
    };
    el('fpWizardCancelBtn').onclick = close;
    el('fpWizardCloseBtn').onclick = close;
    el('fpWizardBackToPickBtn').onclick = () => showStep('pick');

    el('fpWizardConfirmPointBtn').onclick = () => {
      if (points[activePointIndex].pixel_x == null) return;
      openCoordPanel(activePointIndex);
    };

    el('fpWizardNextBtn').onclick = () => {
      const idx = parseInt(el('fpWizardCoordPanel').dataset.pointIndex || '0', 10);
      points[idx].lat = parseFloat(el('fpWizardLat').value);
      points[idx].lng = parseFloat(el('fpWizardLng').value);
      activePointIndex = 1;
      showStep('pick');
      renderMarkers();
    };

    el('fpWizardSaveBtn').onclick = saveGeoref;

    el('fpWizardZoomIn').onclick = () => {
      const vp = el('fpWizardViewport');
      const r = vp.getBoundingClientRect();
      zoomAt(1.2, r.left + r.width / 2, r.top + r.height / 2);
    };
    el('fpWizardZoomOut').onclick = () => {
      const vp = el('fpWizardViewport');
      const r = vp.getBoundingClientRect();
      zoomAt(1 / 1.2, r.left + r.width / 2, r.top + r.height / 2);
    };
    el('fpWizardZoomReset').onclick = fitViewToImage;

    const vp = el('fpWizardViewport');
    vp.addEventListener('click', handleMapClick);
    vp.addEventListener('mousemove', handleCrosshairMove);
    vp.addEventListener('mouseleave', () => { el('fpWizardCrosshair').style.display = 'none'; });
    vp.addEventListener('wheel', onWheel, { passive: false });
    vp.addEventListener('pointerdown', onPointerDown);
    vp.addEventListener('pointermove', onPointerMove);
    vp.addEventListener('pointerup', onPointerUp);
    vp.addEventListener('pointercancel', onPointerUp);
    vp.addEventListener('contextmenu', (e) => { if (step === 'pick') e.preventDefault(); });

    el('fpCoordWizardModal').addEventListener('click', (e) => {
      if (e.target === el('fpCoordWizardModal')) close();
    });

    window.addEventListener('resize', () => {
      if (step === 'pick' || step === 'coords') fitViewToImage();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return { open, close };
})();

window.FpCoordWizard = FpCoordWizard;
