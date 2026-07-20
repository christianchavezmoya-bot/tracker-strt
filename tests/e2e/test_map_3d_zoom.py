"""
3D map — zoom parity, view sync, focus tracker.
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("PLAYWRIGHT_E2E") != "1",
    reason="Set PLAYWRIGHT_E2E=1 to run browser smoke tests",
)


def _wait_map(page):
    page.wait_for_selector("#map2d", state="visible", timeout=20000)
    for _ in range(40):
        if page.evaluate("() => !!(window._map2d && window.ensureMap3D)"):
            return
        page.wait_for_timeout(500)
    pytest.fail("Map did not initialize")


def test_3d_view_syncs_from_2d_zoom(logged_in_page, e2e_base):
    page = logged_in_page
    page.goto(f"{e2e_base}/")
    _wait_map(page)

    assert page.evaluate(
        "() => typeof window.camDistForZoom2D === 'function'"
        " && typeof window.sync3DCameraFrom2D === 'function'"
    )

    page.click('.view-btn[data-view="3d"]')
    page.wait_for_timeout(3000)
    assert page.evaluate("() => !!window._map3dReady")

    before = page.evaluate("() => window.zoom2DForCamDist(window.get3DCameraState().dist)")
    page.evaluate("() => window.zoom3DByWheelDelta(-120)")
    page.wait_for_timeout(300)
    after = page.evaluate("() => window.zoom2DForCamDist(window.get3DCameraState().dist)")
    assert after > before, f"3D zoom in should increase equiv 2D zoom: {before} -> {after}"


def test_3d_focus_tracker_centers_camera(logged_in_page, e2e_base):
    page = logged_in_page
    page.goto(f"{e2e_base}/")
    _wait_map(page)
    page.click('.view-btn[data-view="3d"]')
    page.wait_for_timeout(2500)

    result = page.evaluate(
        """() => {
          const t = Object.values(window.trackers || {}).find(
            tr => tr.pos_x != null && tr.pos_y != null
          );
          if (!t) return { skipped: true };
          window.focus3DTracker(t.id);
          const cam = window.get3DCameraState();
          const d = window.HoloCoords.realToDisplay(t.pos_x, t.pos_y);
          return {
            skipped: false,
            targetX: cam.targetX,
            targetZ: cam.targetZ,
            expectX: d.mapX,
            expectZ: d.mapY,
            dist: cam.dist,
          };
        }"""
    )
    if result.get("skipped"):
        pytest.skip("No trackers with positions in demo data")
    assert abs(result["targetX"] - result["expectX"]) < 0.05
    assert abs(result["targetZ"] - result["expectZ"]) < 0.05
    assert result["dist"] < 100
