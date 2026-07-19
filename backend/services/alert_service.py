"""
HOLO-RTLS — Alert Service
Evaluates position updates and fires alerts for:
  - Restricted zone entry
  - No signal / tag offline
  - Low battery
  - Environmental hazards
  - Node offline

Integrated into the IngestionLoop — runs after every position update.
Also runs periodic checks for offline tags and nodes.
"""
from __future__ import annotations
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ── Geometry helpers ───────────────────────────────────────────────────────────

def point_in_polygon(x: float, y: float, polygon: List[Tuple[float, float]]) -> bool:
    """
    Ray-casting point-in-polygon test.
    polygon: list of (x, y) vertices in order (clockwise or CCW).
    Returns True if (x, y) is inside the polygon.
    """
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def point_in_sphere(x: float, y: float, z: float,
                    cx: float, cy: float, cz: float,
                    radius: float) -> bool:
    """True if (x,y,z) is within radius of (cx,cy,cz)."""
    dx = x - cx; dy = y - cy; dz = z - cz
    return (dx*dx + dy*dy + dz*dz) <= radius * radius


# ── Alert event ────────────────────────────────────────────────────────────────

@dataclass
class AlertEvent:
    tracker_id: int
    alert_type: int          # AlertType enum value
    message: str
    pos_x: float
    pos_y: float
    pos_z: float
    section_name: Optional[str] = None
    zone_name: Optional[str] = None
    node_id: Optional[int] = None


# ── Alert Service ─────────────────────────────────────────────────────────────

class AlertService:
    """
    Evaluates position updates against alert rules.
    Thread-safe. Integrates with the IngestionLoop via evaluate_position().
    Runs periodic checks (offline, battery) in a background thread.
    """

    def __init__(self, db_session, app: Flask = None,
                 no_signal_timeout: int = 120,       # seconds
                 check_interval: int = 30):          # periodic check interval
        self._db = db_session
        self._app = app
        self._no_signal_timeout = no_signal_timeout
        self._check_interval = check_interval

        # Track which alerts have already fired (debounce)
        # key = (tracker_id, alert_type) → last_fired_at
        self._fired: Dict[Tuple[int, int], datetime] = {}
        # Debounce window in seconds
        self._debounce_seconds = 60

        # Track last seen timestamp per tracker
        self._last_seen: Dict[int, datetime] = {}

        # Track zones and sections (re-fetched periodically to avoid stale data)
        self._zones_cache: List[object] = []
        self._sections_cache: List[object] = []
        self._last_zone_reload = datetime.min.replace(tzinfo=timezone.utc)
        self._zone_cache_ttl = 60  # seconds

        # Alert count stats
        self._stats = {"fired": 0, "suppressed": 0}

        # Periodic check thread
        self._stop = threading.Event()
        self._check_thread = threading.Thread(
            target=self._periodic_check, daemon=True, name="AlertPeriodicCheck"
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        self._reload_zones()
        self._check_thread.start()
        logger.info("AlertService started")

    def stop(self):
        self._stop.set()
        self._check_thread.join(timeout=5)
        logger.info("AlertService stopped")

    # ── Zone cache ─────────────────────────────────────────────────────────────

    def _reload_zones(self):
        """Re-fetch zones and sections from DB (snapshot plain values — session-safe)."""
        with self._app.app_context():
            from backend.models import Zone, MapSection
            from sqlalchemy.orm import joinedload
            try:
                zones = self._db.query(Zone).options(joinedload(Zone.section)).filter(
                    Zone.zone_type.in_([2, 5])   # RESTRICTED=2, DANGER=5
                ).all()
                snapped = []
                for z in zones:
                    try:
                        sec_name = z.section.name if z.section else None
                    except Exception:
                        sec_name = None
                    snapped.append(type("ZoneSnap", (), {
                        "name": z.name,
                        "pos_x": z.pos_x,
                        "pos_y": z.pos_y,
                        "pos_z": z.pos_z or 0.0,
                        "radius": z.radius or 0.0,
                        "section_name": sec_name,
                    })())
                self._zones_cache = snapped
                self._sections_cache = self._db.query(MapSection).filter(
                    MapSection.is_restricted == True
                ).all()
                self._last_zone_reload = datetime.now(timezone.utc)
                logger.debug(f"AlertService: {len(self._zones_cache)} restricted zones, "
                             f"{len(self._sections_cache)} restricted sections")
            except Exception as e:
                logger.error(f"Failed to reload zones: {e}")

    def _ensure_zones_fresh(self):
        age = (datetime.now(timezone.utc) - self._last_zone_reload).total_seconds()
        if age > self._zone_cache_ttl:
            self._reload_zones()

    # ── Main evaluation entry point ───────────────────────────────────────────

    def evaluate_position(self, tracker_id: int,
                         x: float, y: float, z: float,
                         hardware_id: str = None,
                         battery: float = None,
                         env_data: dict = None):
        """
        Called by IngestionLoop after every position update.
        Evaluates all alert conditions and yields AlertEvents.

        Args:
            tracker_id: DB tracker id
            x, y, z: Position in real-world meters
            hardware_id: Hardware identifier
            battery: Battery level 0–100 (optional)
            env_data: Environmental data dict (temp, gas, etc.)
        """
        self._ensure_zones_fresh()
        self._last_seen[tracker_id] = datetime.now(timezone.utc)

        # Run evaluations in order of priority
        alerts: List[AlertEvent] = []

        # 1. Restricted zone entry (sphere zones)
        alerts.extend(self._check_zone_violation(tracker_id, x, y, z))

        # 2. Restricted section entry (polygon sections)
        alerts.extend(self._check_section_violation(tracker_id, x, y))

        # 3. Low battery
        if battery is not None:
            alerts.extend(self._check_low_battery(tracker_id, battery))

        # 4. Environmental hazard
        if env_data:
            alerts.extend(self._check_env_hazard(tracker_id, env_data, x, y, z))

        # 5. Proximity (tag-to-tag)
        alerts.extend(self._check_proximity(tracker_id, x, y, z))

        # Fire non-suppressed alerts
        for alert in alerts:
            if self._should_fire(tracker_id, alert.alert_type):
                self._fired[(tracker_id, alert.alert_type)] = datetime.now(timezone.utc)
                self._fire_alert(alert)
                self._stats["fired"] += 1
            else:
                self._stats["suppressed"] += 1

    def _should_fire(self, tracker_id: int, alert_type: int) -> bool:
        """Debounce: only fire if enough time has passed since last fire."""
        key = (tracker_id, alert_type)
        last = self._fired.get(key)
        if last is None:
            return True
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return elapsed >= self._debounce_seconds

    # ── Alert condition checks ─────────────────────────────────────────────────

    def _check_zone_violation(self, tracker_id: int,
                               x: float, y: float, z: float) -> List[AlertEvent]:
        """Check if tracker entered any restricted sphere zone."""
        alerts = []
        for zone in self._zones_cache:
            if point_in_sphere(x, y, z,
                               zone.pos_x, zone.pos_y, zone.pos_z,
                               zone.radius):
                alerts.append(AlertEvent(
                    tracker_id=tracker_id,
                    alert_type=3,   # RESTRICTED_ZONE
                    message=f"Tracker entered restricted zone: {zone.name}",
                    pos_x=x, pos_y=y, pos_z=z,
                    section_name=getattr(zone, "section_name", None),
                    zone_name=zone.name,
                ))
        return alerts

    def _check_section_violation(self, tracker_id: int,
                                   x: float, y: float) -> List[AlertEvent]:
        """Check if tracker entered any restricted section polygon."""
        alerts = []
        for section in self._sections_cache:
            polygon_json = getattr(section, "polygon_json", None)
            if not polygon_json:
                continue
            try:
                import json
                coords = json.loads(polygon_json)
                # Support GeoJSON format or simple list
                if isinstance(coords, dict):
                    coords = coords.get("coordinates", [])
                if not coords:
                    continue
                # First ring only for now
                ring = coords[0] if isinstance(coords[0], list) else coords
                if point_in_polygon(x, y, ring):
                    alerts.append(AlertEvent(
                        tracker_id=tracker_id,
                        alert_type=3,   # RESTRICTED_ZONE
                        message=f"Tracker entered restricted section: {section.name}",
                        pos_x=x, pos_y=y, pos_z=0.0,
                        section_name=section.name,
                    ))
            except Exception as e:
                logger.warning(f"Section polygon parse error: {e}")
        return alerts

    def _check_low_battery(self, tracker_id: int, battery: float) -> List[AlertEvent]:
        """Low battery alert at 20% and 10%."""
        alerts = []
        threshold = 20 if battery < 20 else (10 if battery < 10 else None)
        if threshold:
            alerts.append(AlertEvent(
                tracker_id=tracker_id,
                alert_type=4,   # LOW_BATTERY
                message=f"Tracker battery at {battery:.0f}%",
                pos_x=0.0, pos_y=0.0, pos_z=0.0,
            ))
        return alerts

    def _check_env_hazard(self, tracker_id: int,
                          env_data: dict,
                          x: float, y: float, z: float) -> List[AlertEvent]:
        """Environmental hazard alerts from sensor data."""
        alerts = []

        # Gas / VOC threshold
        voc = env_data.get("voc", 0)
        if voc > 500:  # ppb — threshold is configurable
            alerts.append(AlertEvent(
                tracker_id=tracker_id,
                alert_type=6,   # ENV_HAZARD
                message=f"High VOC detected: {voc} ppb",
                pos_x=x, pos_y=y, pos_z=z,
            ))

        # Temperature
        temp = env_data.get("temperature")
        if temp is not None and temp > 40.0:  # Celsius
            alerts.append(AlertEvent(
                tracker_id=tracker_id,
                alert_type=6,
                message=f"High temperature: {temp:.1f}°C",
                pos_x=x, pos_y=y, pos_z=z,
            ))

        return alerts

    def _check_proximity(self, tracker_id: int,
                         x: float, y: float, z: float) -> List[AlertEvent]:
        """Warn when two active trackers are closer than proximity threshold."""
        import os
        try:
            threshold = float(os.getenv("PROXIMITY_ALERT_METERS", "2.0"))
        except ValueError:
            threshold = 2.0
        if threshold <= 0:
            return []

        alerts = []
        try:
            from backend.models import Tracker, Setting
            # Optional override from settings
            setting = Setting.query.filter_by(key="proximity_meters").first()
            if setting and setting.value:
                try:
                    threshold = float(setting.value)
                except ValueError:
                    pass

            others = Tracker.query.filter(Tracker.id != tracker_id).all()
            for other in others:
                ox = getattr(other, "pos_x", None)
                oy = getattr(other, "pos_y", None)
                if ox is None or oy is None:
                    continue
                dist = ((x - ox) ** 2 + (y - oy) ** 2) ** 0.5
                if dist <= threshold:
                    name = other.assigned_name or other.hardware_id or f"#{other.id}"
                    alerts.append(AlertEvent(
                        tracker_id=tracker_id,
                        alert_type=9,  # PROXIMITY
                        message=f"Proximity warning: within {dist:.1f}m of {name} (limit {threshold}m)",
                        pos_x=x, pos_y=y, pos_z=z,
                    ))
                    break  # one proximity alert per evaluation
        except Exception as e:
            logger.warning("Proximity check failed: %s", e)
        return alerts

    def _check_no_signal(self, tracker_id: int,
                         x: float, y: float, z: float) -> List[AlertEvent]:
        """Tracker hasn't reported in no_signal_timeout seconds."""
        last = self._last_seen.get(tracker_id)
        if last is None:
            return []
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        if elapsed >= self._no_signal_timeout:
            return [AlertEvent(
                tracker_id=tracker_id,
                alert_type=1,   # NO_SIGNAL
                message=f"No signal for {int(elapsed)} seconds",
                pos_x=x, pos_y=y, pos_z=z,
            )]
        return []

    # ── Alert broadcasting ──────────────────────────────────────────────────────

    def set_sse_broadcaster(self, broadcast_fn):
        """
        Register a callback to broadcast SSE events.
        Called by the ingestion loop during service wiring.
        broadcast_fn(alert: Alert) — sends the alert to all SSE clients.
        """
        self._sse_broadcast = broadcast_fn

    # ── Periodic check thread ──────────────────────────────────────────────────

    def _periodic_check(self):
        """Run offline / no-signal checks every _check_interval seconds."""
        while not self._stop.is_set():
            time.sleep(self._check_interval)
            if self._stop.is_set():
                break
            try:
                self._run_offline_checks()
            except Exception as e:
                logger.error(f"AlertService periodic check error: {e}")

    def _run_offline_checks(self):
        """Check all trackers for no-signal condition."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self._no_signal_timeout)

        with self._app.app_context():
            from backend.models import Tracker, AssetState
            try:
                # Find trackers that haven't reported
                trackers = self._db.query(Tracker).filter(
                    Tracker.asset_state == AssetState.ACTIVE
                ).all()

                for tracker in trackers:
                    last_seen = self._last_seen.get(tracker.id)
                    if last_seen is None or last_seen < cutoff:
                        key = (tracker.id, 1)   # AlertType.NO_SIGNAL
                        if self._should_fire(tracker.id, 1):
                            self._fired[key] = now
                            self._fire_alert(AlertEvent(
                                tracker_id=tracker.id,
                                alert_type=1,
                                message=f"Tracker '{tracker.name}' ({tracker.hardware_id}) offline",
                                pos_x=0.0, pos_y=0.0, pos_z=0.0,
                            ))
                            self._stats["fired"] += 1
                        else:
                            self._stats["suppressed"] += 1
            except Exception as e:
                logger.error(f"Offline check error: {e}")

    # ── Alert firing ──────────────────────────────────────────────────────────

    def _fire_alert(self, event: AlertEvent):
        """Write alert to DB and dispatch notifications."""
        if not self._app:
            logger.warning("AlertService: no Flask app — alert not written")
            return

        with self._app.app_context():
            from backend.models import Alert, AlertState
            from backend.extensions import db

            alert = Alert(
                tracker_id=event.tracker_id,
                node_id=event.node_id,
                alert_type=event.alert_type,
                state=AlertState.ACTIVE,
                message=event.message,
                pos_x=event.pos_x,
                pos_y=event.pos_y,
                pos_z=event.pos_z,
                section_name=event.section_name,
            )
            db.session.add(alert)
            db.session.commit()

            # Notify via SSE (broadcast to all connected browsers)
            self._broadcast_alert(alert)

            # Schedule email/SMS dispatch
            self._dispatch_notifications(alert)

            # Webhooks (best-effort)
            try:
                from backend.api.webhooks import dispatch_webhooks
                payload = {
                    "id": alert.id,
                    "tracker_id": alert.tracker_id,
                    "alert_type": alert.alert_type,
                    "message": alert.message,
                    "pos_x": alert.pos_x,
                    "pos_y": alert.pos_y,
                    "zone_name": event.zone_name,
                    "section_name": event.section_name,
                }
                dispatch_webhooks("alert.created", payload)
                if event.alert_type == 3 and event.zone_name:
                    dispatch_webhooks("zone.enter", payload)
            except Exception as we:
                logger.warning("Webhook dispatch failed: %s", we)

            logger.info(f"[ALERT] tracker={event.tracker_id} type={event.alert_type} msg={event.message}")

    def _broadcast_alert(self, alert):
        """Push alert event to all SSE clients."""
        broadcaster = getattr(self, '_sse_broadcast', None)
        if callable(broadcaster):
            try:
                broadcaster(alert)
                return
            except Exception as e:
                logger.error(f"SSE broadcast error: {e}")
        from backend.services.ingestion_loop import get_ingestion_loop
        loop = get_ingestion_loop()
        if not loop:
            return
        loop._broadcast_sse({"type": "alert", "alert": alert.to_dict()})

    def _dispatch_notifications(self, alert):
        """Send in-app + email/SMS notifications for the alert."""
        from backend.services.notification_service import get_notification_service
        svc = get_notification_service()
        if svc:
            svc.notify_alert(alert)

    # ── Stats ────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "debounced_count": sum(
                1 for (tid, at), last in self._fired.items()
                if (datetime.now(timezone.utc) - last).total_seconds() < 60
            ),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_alert_service: Optional[AlertService] = None


def get_alert_service() -> Optional[AlertService]:
    return _alert_service


def init_alert_service(db_session, app: Flask, **kwargs) -> AlertService:
    global _alert_service
    _alert_service = AlertService(db_session, app, **kwargs)
    return _alert_service
