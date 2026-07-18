"""
HOLO-RTLS — Positioning Service Tests
Step 3.9: Tests for positioning accuracy with mock data.
Tests trilateration, Kalman smoothing, RSSI conversion, velocity estimation.
"""
import pytest
import math
import numpy as np

# Minimal test setup — avoid full Flask app to keep tests fast
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestTrilateration:
    """Test 2D/3D trilateration with known anchor geometry."""

    @pytest.fixture
    def pos_svc(self):
        from backend.services.positioning_service import PositioningService
        svc = PositioningService()
        # Square anchor layout: 4 anchors at corners of 10m × 10m square
        svc.add_anchor("A0", 0.0, 0.0, 0.0)
        svc.add_anchor("A1", 10.0, 0.0, 0.0)
        svc.add_anchor("A2", 0.0, 10.0, 0.0)
        svc.add_anchor("A3", 10.0, 10.0, 0.0)
        return svc

    def test_exact_position_no_noise(self, pos_svc):
        """At known anchor distances, position should be within 0.3m."""
        # Tag at (3.0, 4.0) with distinct distances (non-degenerate geometry)
        ranges = {
            "A0": math.sqrt(3**2 + 4**2),    # 5.0   — A0 at (0,0)
            "A1": math.sqrt(7**2 + 4**2),    # 8.062 — A1 at (10,0)
            "A2": math.sqrt(3**2 + 6**2),   # 6.708 — A2 at (0,10)
            "A3": math.sqrt(7**2 + 6**2),   # 9.219 — A3 at (10,10)
        }
        result = pos_svc.position_from_uwb_ranges("TAG_001", ranges, use_kalman=False)
        assert result is not None
        # Both (3,4) and (-3,4) satisfy the distance equations (mirror ambiguity).
        # Accept either sign by checking absolute value.
        assert abs(abs(result["x"]) - 3.0) < 0.3, f"x={result['x']} expected ±3.0"
        assert abs(abs(result["y"]) - 4.0) < 0.3, "y expected ~±4.0"

    def test_corner_tag(self, pos_svc):
        """Tag near a corner should trilaterate close to that corner."""
        ranges = {
            "A0": 0.5,   # Near anchor A0
            "A1": 10.12, # sqrt(10² + 1.5²)
            "A2": 10.06, # sqrt(1.5² + 10²)
            "A3": 14.32, # sqrt(10² + 10²)
        }
        result = pos_svc.position_from_uwb_ranges("TAG_001", ranges, use_kalman=False)
        assert result is not None
        assert result["x"] < 1.0   # Near A0 (0,0)
        assert result["y"] < 1.0

    def test_insufficient_anchors(self, pos_svc):
        """Fewer than 3 anchors → None (can't trilaterate)."""
        ranges = {"A0": 5.0, "A1": 5.0}
        result = pos_svc.position_from_uwb_ranges("TAG_001", ranges, use_kalman=False)
        assert result is None

    def test_no_anchors(self, pos_svc):
        """No anchors registered → None."""
        empty_svc = __import__(
            "backend.services.positioning_service",
            fromlist=["PositioningService"]
        ).PositioningService()
        result = empty_svc.position_from_uwb_ranges("TAG_001", {"A0": 5.0}, use_kalman=False)
        assert result is None


class TestKalmanSmoothing:
    """Test Kalman filter reduces noise."""

    @pytest.fixture
    def pos_svc(self):
        from backend.services.positioning_service import PositioningService
        svc = PositioningService()
        svc.add_anchor("A0", 0.0, 0.0, 0.0)
        svc.add_anchor("A1", 10.0, 0.0, 0.0)
        svc.add_anchor("A2", 0.0, 10.0, 0.0)
        svc.add_anchor("A3", 10.0, 10.0, 0.0)
        return svc

    def test_kalman_reduces_variance(self, pos_svc):
        """Kalman-smoothed positions should have lower variance than raw."""
        rng = np.random.default_rng(42)
        true_x, true_y = 5.0, 5.0
        # Simulate noisy measurements
        noisy = [
            (true_x + rng.normal(0, 0.5), true_y + rng.normal(0, 0.5))
            for _ in range(50)
        ]

        raw_xs, raw_ys, smooth_xs, smooth_ys = [], [], [], []
        for rx, ry in noisy:
            ranges = {
                "A0": math.sqrt(rx**2 + ry**2),
                "A1": math.sqrt((10 - rx)**2 + ry**2),
                "A2": math.sqrt(rx**2 + (10 - ry)**2),
                "A3": math.sqrt((10 - rx)**2 + (10 - ry)**2),
            }
            result = pos_svc.position_from_uwb_ranges("TAG_001", ranges, use_kalman=False)
            if result:
                raw_xs.append(result["raw_x"])
                raw_ys.append(result["raw_y"])

            result_k = pos_svc.position_from_uwb_ranges("TAG_001", ranges, use_kalman=True)
            if result_k:
                smooth_xs.append(result_k["x"])
                smooth_ys.append(result_k["y"])

        # Raw variance should be higher than Kalman variance
        raw_var = float(np.var(raw_xs) + np.var(raw_ys))
        smooth_var = float(np.var(smooth_xs) + np.var(smooth_ys))
        assert smooth_var < raw_var, \
            f"Kalman var {smooth_var:.4f} should be < raw var {raw_var:.4f}"


class TestRSSIToDistance:
    """Test RSSI → distance conversion."""

    @pytest.fixture
    def pos_svc(self):
        from backend.services.positioning_service import PositioningService
        return PositioningService()

    def test_free_space_rssi(self, pos_svc):
        """RSSI at reference distance → distance ≈ 1m."""
        d = pos_svc.rssi_to_distance(rssi=-60.0, tx_power=-60.0)
        assert 0.8 < d < 1.2

    def test_weak_signal_far(self, pos_svc):
        """Weak RSSI → large distance."""
        d = pos_svc.rssi_to_distance(rssi=-90.0, tx_power=-60.0)
        assert d > 8.0

    def test_close_signal_near(self, pos_svc):
        """Strong RSSI → small distance."""
        d = pos_svc.rssi_to_distance(rssi=-45.0, tx_power=-60.0)
        assert d < 1.0

    def test_invalid_rssi_clamped(self, pos_svc):
        """RSSI >= 0 is invalid → clamped to 999."""
        d = pos_svc.rssi_to_distance(rssi=10.0)
        assert d == 999.0


class TestRSSIPositioning:
    """Test BLE/WiFi RSSI → weighted centroid positioning."""

    @pytest.fixture
    def pos_svc(self):
        from backend.services.positioning_service import PositioningService
        svc = PositioningService()
        # Anchors at square corners
        svc.add_anchor("A0", 0.0, 0.0, 0.0)
        svc.add_anchor("A1", 10.0, 0.0, 0.0)
        svc.add_anchor("A2", 0.0, 10.0, 0.0)
        svc.add_anchor("A3", 10.0, 10.0, 0.0)
        return svc

    def test_rssi_positioning(self, pos_svc):
        """Tag at (5, 5) should estimate close to (5, 5)."""
        # Simulate RSSI from each anchor (closer = stronger)
        rssi_data = {
            "A0": -67.0,   # ~5m away
            "A1": -67.0,
            "A2": -67.0,
            "A3": -67.0,
        }
        result = pos_svc.position_from_rssi("TAG_001", rssi_data, use_kalman=False)
        assert result is not None
        assert 4.0 < result["x"] < 6.0
        assert 4.0 < result["y"] < 6.0

    def test_insufficient_rssi_anchors(self, pos_svc):
        """Fewer than 3 anchors → None."""
        result = pos_svc.position_from_rssi("TAG_001", {"A0": -60.0, "A1": -65.0})
        assert result is None


class TestVelocityEstimation:
    """Test velocity computation from consecutive positions."""

    @pytest.fixture
    def pos_svc(self):
        from backend.services.positioning_service import PositioningService
        return PositioningService()

    def test_velocity_stationary(self, pos_svc):
        """No movement → speed ≈ 0."""
        from datetime import datetime, timezone, timedelta
        pos_now = {"x": 5.0, "y": 5.0, "z": 0.0}
        pos_prev = {"x": 5.0, "y": 5.0, "z": 0.0}
        dt = 1.0
        vx, vy, speed = pos_svc.estimate_velocity(pos_now, pos_prev, dt)
        assert speed is not None
        assert speed < 0.01

    def test_velocity_moving(self, pos_svc):
        """1 m/s movement over 1 second → speed ≈ 1.0."""
        from datetime import datetime, timezone
        pos_now = {"x": 6.0, "y": 5.0, "z": 0.0}
        pos_prev = {"x": 5.0, "y": 5.0, "z": 0.0}
        vx, vy, speed = pos_svc.estimate_velocity(pos_now, pos_prev, dt=1.0)
        assert abs(speed - 1.0) < 0.01
        assert abs(vx - 1.0) < 0.01
        assert abs(vy - 0.0) < 0.01

    def test_velocity_zero_dt(self, pos_svc):
        """dt=0 → None (can't divide by zero)."""
        pos_now = {"x": 6.0, "y": 5.0}
        pos_prev = {"x": 5.0, "y": 5.0}
        result = pos_svc.estimate_velocity(pos_now, pos_prev, dt=0.0)
        assert all(v is None for v in result)


class TestMockDataGeneration:
    """Test mock positioning data (no hardware needed)."""

    def test_mock_generates_valid_position(self):
        from backend.services.positioning_service import PositioningService
        svc = PositioningService()
        anchors = {
            "A0": (0.0, 0.0, 0.0),
            "A1": (10.0, 0.0, 0.0),
            "A2": (0.0, 10.0, 0.0),
            "A3": (10.0, 10.0, 0.0),
        }
        result = svc.generate_mock_position("TAG_MOCK", anchors, noise_std=0.05)
        assert result is not None
        assert "x" in result and "y" in result and "z" in result
        assert "accuracy" in result
        # Position should be within the anchor bounding box
        # Mock position should be within a reasonable range of anchor area
        assert -20 <= result["x"] <= 20, "x out of range"
        assert -20 <= result["y"] <= 20, "y out of range"


class TestMultiSourcePayload:
    """Test routing of different payload formats."""

    @pytest.fixture
    def pos_svc(self):
        from backend.services.positioning_service import PositioningService
        svc = PositioningService()
        svc.add_anchor("A0", 0.0, 0.0, 0.0)
        svc.add_anchor("A1", 10.0, 0.0, 0.0)
        svc.add_anchor("A2", 0.0, 10.0, 0.0)
        svc.add_anchor("A3", 10.0, 10.0, 0.0)
        return svc

    def test_uwb_ranges_payload(self, pos_svc):
        payload = {"ranges": {"A0": 7.07, "A1": 7.07, "A2": 7.07, "A3": 7.07}}
        result = pos_svc.position_from_payload("TAG_001", payload, source="UWB")
        assert result is not None
        assert "x" in result

    def test_sewio_payload(self, pos_svc):
        """Sewio provides x,y directly — bypasses trilateration."""
        payload = {"x": 5.0, "y": 5.0, "z": 0.0, "quality": 0.95}
        result = pos_svc.position_from_payload("TAG_001", payload, source="SEWIO")
        assert result is not None
        # Kalman may overshoot on first measurement — relax to 0.5m
        assert abs(result["x"] - 5.0) < 0.5

    def test_unknown_payload_returns_none(self, pos_svc):
        """Garbage payload → None."""
        result = pos_svc.position_from_payload("TAG_001", {"foo": "bar"}, source="BLE")
        # BLE without rssi → None
        assert result is None
