"""
Map layer smoke — street/satellite toggles with uploaded floor plan.
"""
import io
import os
import time

import pytest
from PIL import Image

pytestmark = pytest.mark.skipif(
    os.getenv("PLAYWRIGHT_E2E") != "1",
    reason="Set PLAYWRIGHT_E2E=1 to run browser smoke tests",
)


def _wait_map(page, timeout_ms=30000):
    page.wait_for_selector("#map2d", state="visible", timeout=timeout_ms)
    for _ in range(40):
        if page.evaluate("() => !!(window._map2d && window.toggleStreetBasemap)"):
            return
        page.wait_for_timeout(500)
    pytest.fail("Map did not initialize")


def _upload_plan(page):
    return page.evaluate(
        """async () => {
          const res = await fetch('/api/zones/sections');
          const data = await res.json();
          const hasPlan = data.items?.[0]?.image_url && !data.items[0].image_url.includes('placeholder');
          return { hasPlan };
        }"""
    )


def _diag(page):
    return page.evaluate(
        """() => {
          const map = window._map2d;
          if (!map) return { error: 'no map' };
          let images = 0, tiles = 0;
          map.eachLayer(l => {
            const cls = l.constructor?.name;
            if (cls === 'ImageOverlay' || (l._url && !String(l._url).includes('tile'))) images++;
            if (cls === 'TileLayer') tiles++;
          });
          return {
            view: window.MapGeoref?.getViewMode?.(),
            georef: window.MapGeoref?.isGeoref?.(),
            streetHandler: window.toggleStreetMapLayer?.constructor?.name,
            basemapHandler: typeof window.toggleStreetBasemap,
            layerState: window.layerState?.streetMap,
            streetChecked: document.getElementById('layerStreetMap')?.checked,
            images,
            tiles,
            domTiles: document.querySelectorAll('.leaflet-tile-pane img').length,
            trackerCanvas: !!document.querySelector('.tracker-canvas-layer'),
          };
        }"""
    )


def test_street_layer_checkbox_switches_to_regional(logged_in_page, e2e_base):
    page = logged_in_page
    page.goto(f"{e2e_base}/")
    _wait_map(page)

    assert page.evaluate("() => typeof window.toggleStreetMapLayer === 'function'")
    assert page.evaluate("() => typeof window.toggleStreetBasemap === 'function'")
    assert page.evaluate(
        "() => window.toggleStreetMapLayer !== window.toggleStreetBasemap"
    ), "Layer orchestrator must differ from low-level basemap toggle"

    page.click("#layersBtn")
    page.check("#layerStreetMap")
    page.wait_for_timeout(3500)

    d = _diag(page)
    assert d["view"] == "regional", d
    assert d["layerState"] is True, d
    assert d["tiles"] >= 1 or d["images"] >= 1, d


def test_georef_overlay_survives_zoom_and_satellite(logged_in_page, e2e_base):
    page = logged_in_page
    page.evaluate(
        """async () => {
          await API.post('/positioning/calibration', {
            section_id: 0,
            georef_points: [
              { pixel_x: 0, pixel_y: 0, lat: -32.214525, lng: 149.808612 },
              { pixel_x: 800, pixel_y: 600, lat: -32.340944, lng: 149.759408 },
            ],
          });
        }"""
    )
    page.goto(f"{e2e_base}/?t={int(time.time())}")
    _wait_map(page)
    page.click("#layersBtn")
    page.check("#layerStreetMap")
    page.wait_for_timeout(3000)

    before = _diag(page)
    assert before["georef"] is True
    assert before["images"] >= 1

    for _ in range(4):
        page.click(".leaflet-control-zoom-in")
        page.wait_for_timeout(250)
    page.check("#layerSatellite")
    page.wait_for_timeout(2500)

    after = _diag(page)
    assert after["images"] >= 1, after
    assert after["view"] == "regional", after
    assert after["domTiles"] >= 1 or after["tiles"] >= 1, after
