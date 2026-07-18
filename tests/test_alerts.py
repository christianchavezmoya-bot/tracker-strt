"""
HOLO-RTLS — Alert Service Tests
Step 4.7: Tests for alert trigger conditions.
Tests zone violations, no-signal, low battery, env hazard, debounce.
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPointInPolygon:
    """Test ray-casting point-in-polygon algorithm."""

    def test_point_inside_square(self):
        from backend.services.alert_service import point_in_polygon
        # Square: (0,0)-(10,10)
        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert point_in_polygon(5, 5, poly) is True

    def test_point_outside_square(self):
        from backend.services.alert_service import point_in_polygon
        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert point_in_polygon(15, 5, poly) is False

    def test_point_on_edge(self):
        from backend.services.alert_service import point_in_polygon
        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        # On edge — result depends on ray crossing parity
        result = point_in_polygon(5, 0, poly)
        assert isinstance(result, bool)

    def test_concave_polygon(self):
        from backend.services.alert_service import point_in_polygon
        # L-shaped polygon: bottom strip (0,0)-(5,10) + right strip (5,5)-(10,10)
        poly = [(0, 0), (5, 0), (5, 5), (10, 5), (10, 10), (0, 10)]
        # (2,2) is inside the left vertical bar
        assert point_in_polygon(2, 2, poly) is True
        # (7,7) is inside the right horizontal bar
        assert point_in_polygon(7, 7, poly) is True
        # (7, 2) is in the notch — outside the L
        assert point_in_polygon(7, 2, poly) is False

    def test_empty_polygon(self):
        from backend.services.alert_service import point_in_polygon
        assert point_in_polygon(5, 5, []) is False
        assert point_in_polygon(5, 5, [(0, 0)]) is False

    def test_ccw_vs_cw_polygon(self):
        from backend.services.alert_service import point_in_polygon
        # Same square, reversed order
        poly_ccw = [(0, 0), (0, 10), (10, 10), (10, 0)]
        poly_cw = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert point_in_polygon(5, 5, poly_ccw) is True
        assert point_in_polygon(5, 5, poly_cw) is True


class TestPointInSphere:
    """Test sphere intersection."""

    def test_inside_sphere(self):
        from backend.services.alert_service import point_in_sphere
        # Center (0,0,0), radius 5
        assert point_in_sphere(3, 0, 0, 0, 0, 0, 5) is True
        assert point_in_sphere(0, 3, 0, 0, 0, 0, 5) is True

    def test_outside_sphere(self):
        from backend.services.alert_service import point_in_sphere
        assert point_in_sphere(10, 0, 0, 0, 0, 0, 5) is False

    def test_on_surface(self):
        from backend.services.alert_service import point_in_sphere
        # Exactly on surface — squared distance == radius²
        assert point_in_sphere(5, 0, 0, 0, 0, 0, 5) is True

    def test_3d_z_coordinate(self):
        from backend.services.alert_service import point_in_sphere
        # 2D in same plane
        assert point_in_sphere(0, 0, 0, 0, 0, 0, 1) is True
        # Z difference too large
        assert point_in_sphere(0, 0, 5, 0, 0, 0, 2) is False


class TestAlertServiceLogic:
    """Test AlertService evaluation logic (no DB needed for geometry checks)."""

    def test_zone_violation_detected(self):
        from backend.services.alert_service import AlertService, point_in_sphere
        # Mock AlertService with no DB — test zone violation check directly
        svc = AlertService.__new__(AlertService)
        svc._app = None
        svc._zones_cache = []
        svc._sections_cache = []

        # Add a restricted zone: center (5,5), radius 2
        class MockZone:
            name = "Test Zone"
            pos_x, pos_y, pos_z = 5.0, 5.0, 0.0
            radius = 2.0
            section = None
        svc._zones_cache.append(MockZone())

        # Inside zone → should fire
        alerts = svc._check_zone_violation(tracker_id=1, x=5.5, y=5.5, z=0.0)
        assert len(alerts) == 1
        assert alerts[0].tracker_id == 1
        assert alerts[0].alert_type == 3  # RESTRICTED_ZONE

    def test_zone_violation_not_fired_when_outside(self):
        from backend.services.alert_service import AlertService
        svc = AlertService.__new__(AlertService)
        svc._app = None
        svc._zones_cache = []
        svc._sections_cache = []

        class MockZone:
            name = "Test Zone"
            pos_x, pos_y, pos_z = 5.0, 5.0, 0.0
            radius = 2.0
            section = None
        svc._zones_cache.append(MockZone())

        # Outside zone
        alerts = svc._check_zone_violation(tracker_id=1, x=10.0, y=10.0, z=0.0)
        assert len(alerts) == 0

    def test_low_battery_at_20_percent(self):
        from backend.services.alert_service import AlertService
        svc = AlertService.__new__(AlertService)
        svc._app = None

        alerts = svc._check_low_battery(tracker_id=1, battery=19.9)
        assert len(alerts) == 1
        assert alerts[0].alert_type == 4  # LOW_BATTERY

    def test_low_battery_at_10_percent(self):
        from backend.services.alert_service import AlertService
        svc = AlertService.__new__(AlertService)
        svc._app = None

        # Should only fire at 10% threshold (not again at 20%)
        alerts = svc._check_low_battery(tracker_id=1, battery=9.9)
        assert len(alerts) == 1
        assert alerts[0].alert_type == 4  # LOW_BATTERY

    def test_battery_ok_no_alert(self):
        from backend.services.alert_service import AlertService
        svc = AlertService.__new__(AlertService)
        svc._app = None

        alerts = svc._check_low_battery(tracker_id=1, battery=50.0)
        assert len(alerts) == 0

    def test_env_hazard_high_voc(self):
        from backend.services.alert_service import AlertService
        svc = AlertService.__new__(AlertService)
        svc._app = None

        alerts = svc._check_env_hazard(
            tracker_id=1,
            env_data={"voc": 600, "temperature": 22},
            x=0, y=0, z=0,
        )
        assert len(alerts) == 1
        assert alerts[0].alert_type == 6  # ENV_HAZARD

    def test_env_hazard_high_temp(self):
        from backend.services.alert_service import AlertService
        svc = AlertService.__new__(AlertService)
        svc._app = None

        alerts = svc._check_env_hazard(
            tracker_id=1,
            env_data={"voc": 100, "temperature": 45},
            x=0, y=0, z=0,
        )
        assert len(alerts) == 1
        assert "45" in alerts[0].message

    def test_env_safe_no_alert(self):
        from backend.services.alert_service import AlertService
        svc = AlertService.__new__(AlertService)
        svc._app = None

        alerts = svc._check_env_hazard(
            tracker_id=1,
            env_data={"voc": 100, "temperature": 22},
            x=0, y=0, z=0,
        )
        assert len(alerts) == 0

    def test_debounce_allows_first_fire(self):
        from backend.services.alert_service import AlertService
        svc = AlertService.__new__(AlertService)
        svc._fired = {}

        # First time → should fire
        assert svc._should_fire(tracker_id=1, alert_type=3) is True

    def test_debounce_suppresses_repeated(self):
        from backend.services.alert_service import AlertService
        from datetime import datetime, timezone
        svc = AlertService.__new__(AlertService)
        svc._fired = {(1, 3): datetime.now(timezone.utc)}  # fired just now
        svc._debounce_seconds = 60

        # Too soon → suppressed
        assert svc._should_fire(tracker_id=1, alert_type=3) is False

    def test_debounce_allows_after_window(self):
        from backend.services.alert_service import AlertService
        from datetime import datetime, timezone, timedelta
        svc = AlertService.__new__(AlertService)
        svc._fired = {(1, 3): datetime.now(timezone.utc) - timedelta(seconds=120)}
        svc._debounce_seconds = 60

        # 2 minutes later → should fire again
        assert svc._should_fire(tracker_id=1, alert_type=3) is True

    def test_different_alert_types_not_debounced_together(self):
        from backend.services.alert_service import AlertService
        from datetime import datetime, timezone
        svc = AlertService.__new__(AlertService)
        svc._fired = {(1, 3): datetime.now(timezone.utc)}  # RESTRICTED_ZONE fired
        svc._debounce_seconds = 60

        # Same tracker, different alert type → should fire
        assert svc._should_fire(tracker_id=1, alert_type=4) is True  # LOW_BATTERY
