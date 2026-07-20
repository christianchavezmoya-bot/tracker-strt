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
  let points = [{}, {}];
  let onComplete = null;

  function el(id) {
    return document.getElementById(id);
  }

  function clickToPixel(img, clientX, clientY) {
    const rect = img.getBoundingClientRect();
    const nw = img.naturalWidth || imageWidth;
    const nh = img.naturalHeight || imageHeight;
    const scale = Math.min(rect.width / nw, rect.height / nh);
    const renderedW = nw * scale;
    const renderedH = nh * scale;
    const offsetX = (rect.width - renderedW) / 2;
    const offsetY = (rect.height - renderedH) / 2;
    const relX = clientX - rect.left - offsetX;
    const relY = clientY - rect.top - offsetY;
    if (relX < 0 || relY < 0 || relX > renderedW || relY > renderedH) return null;
    return {
      pixel_x: (relX / renderedW) * nw,
      pixel_y: (relY / renderedH) * nh,
    };
  }

  function markerPosition(img, px, py) {
    const rect = img.getBoundingClientRect();
    const nw = img.naturalWidth || imageWidth;
    const nh = img.naturalHeight || imageHeight;
    const scale = Math.min(rect.width / nw, rect.height / nh);
    const renderedW = nw * scale;
    const renderedH = nh * scale;
    const offsetX = (rect.width - renderedW) / 2;
    const offsetY = (rect.height - renderedH) / 2;
    return {
      left: offsetX + (px / nw) * renderedW,
      top: offsetY + (py / nh) * renderedH,
    };
  }

  function showStep(name) {
    step = name;
    el('fpWizardIntro').style.display = name === 'intro' ? 'block' : 'none';
    el('fpWizardPicker').style.display = (name === 'pick' || name === 'coords') ? 'flex' : 'none';
    el('fpWizardCoordPanel').style.display = name === 'coords' ? 'block' : 'none';
    updatePickerBanner();
  }

  function updatePickerBanner() {
    const banner = el('fpWizardPickBanner');
    if (!banner) return;
    if (step !== 'pick') return;
    const idx = points[0].pixel_x == null ? 0 : 1;
    banner.innerHTML = idx === 0
      ? '<i class="fa-solid fa-crosshairs"></i> Click the <strong>first corner</strong> on your floor plan (e.g. a survey lat/long label)'
      : '<i class="fa-solid fa-crosshairs"></i> Click the <strong>second corner</strong> on the opposite side of the plan';
  }

  function renderMarkers() {
    const layer = el('fpWizardMarkers');
    const img = el('fpWizardImage');
    if (!layer || !img) return;
    layer.innerHTML = '';
    points.forEach((pt, i) => {
      if (pt.pixel_x == null) return;
      const pos = markerPosition(img, pt.pixel_x, pt.pixel_y);
      const dot = document.createElement('div');
      dot.className = 'fp-wizard-marker';
      dot.style.left = pos.left + 'px';
      dot.style.top = pos.top + 'px';
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
    el('fpWizardNextBtn').disabled = !(el('fpWizardLat').value.trim() && el('fpWizardLng').value.trim());
  }

  function bindCoordInputs() {
    const lat = el('fpWizardLat');
    const lng = el('fpWizardLng');
    const sync = () => {
      const ok = lat.value.trim() && lng.value.trim();
      el('fpWizardNextBtn').disabled = !ok;
      el('fpWizardSaveBtn').disabled = !ok;
    };
    lat.oninput = sync;
    lng.oninput = sync;
  }

  function handleImageClick(e) {
    if (step !== 'pick') return;
    const img = el('fpWizardImage');
    const px = clickToPixel(img, e.clientX, e.clientY);
    if (!px) return;
    const idx = points[0].pixel_x == null ? 0 : 1;
    points[idx] = { ...points[idx], pixel_x: px.pixel_x, pixel_y: px.pixel_y };
    renderMarkers();
    openCoordPanel(idx);
  }

  function handleCrosshairMove(e) {
    const overlay = el('fpWizardCrosshair');
    const wrap = el('fpWizardImageWrap');
    if (!overlay || !wrap || step !== 'pick') {
      if (overlay) overlay.style.display = 'none';
      return;
    }
    const rect = wrap.getBoundingClientRect();
    if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) {
      overlay.style.display = 'none';
      return;
    }
    overlay.style.display = 'block';
    overlay.style.left = (e.clientX - rect.left) + 'px';
    overlay.style.top = (e.clientY - rect.top) + 'px';
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
      if (!res || !res.ok) {
        throw new Error((data && data.error) || 'Save failed');
      }
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
    points = [{}, {}];
    step = 'intro';
    onComplete = null;
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
    const modal = el('fpCoordWizardModal');
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    showStep('intro');

    await new Promise((resolve) => {
      const img = el('fpWizardImage');
      img.onload = () => {
        imageWidth = img.naturalWidth || 1000;
        imageHeight = img.naturalHeight || 1000;
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

    el('fpWizardStartBtn').onclick = () => showStep('pick');
    el('fpWizardCancelBtn').onclick = close;
    el('fpWizardCloseBtn').onclick = close;
    el('fpWizardBackToPickBtn').onclick = () => showStep('pick');

    el('fpWizardNextBtn').onclick = () => {
      const idx = parseInt(el('fpWizardCoordPanel').dataset.pointIndex || '0', 10);
      points[idx].lat = parseFloat(el('fpWizardLat').value);
      points[idx].lng = parseFloat(el('fpWizardLng').value);
      showStep('pick');
      renderMarkers();
    };

    el('fpWizardSaveBtn').onclick = saveGeoref;

    el('fpWizardImageWrap').addEventListener('click', handleImageClick);
    el('fpWizardImageWrap').addEventListener('mousemove', handleCrosshairMove);
    el('fpWizardImageWrap').addEventListener('mouseleave', () => {
      const overlay = el('fpWizardCrosshair');
      if (overlay) overlay.style.display = 'none';
    });

    el('fpCoordWizardModal').addEventListener('click', (e) => {
      if (e.target === el('fpCoordWizardModal')) close();
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
