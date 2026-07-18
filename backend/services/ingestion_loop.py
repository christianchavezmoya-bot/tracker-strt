"""
HOLO-RTLS — Ingestion Loop
The central pipeline: Bridge events → Positioning → DB write → SSE broadcast → MQTT sync

Runs as a background thread started by the Flask app factory.
"""
from __future__ import annotations
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Set

from flask import Flask

logger = logging.getLogger(__name__)


class IngestionLoop(threading.Thread):
    """
    Consumes from HardwareBridgeManager.event_queue and:
      1. Routes payload to PositioningService
      2. Writes position to HistoryService (DB)
      3. Evaluates alert conditions (AlertService)
      4. Broadcasts via SSE (Flask response held by SSEClients)
      5. Publishes to MQTT state_changes topic
    """

    def __init__(self,
                 app: Flask,
                 bridge_manager,
                 positioning_service,
                 history_service,
                 floor_plan_mapper,
                 mqtt_client=None,
                 alert_service=None,
                 flush_interval: float = 0.1):
        super().__init__(daemon=True, name="IngestionLoop")
        self._app = app
        self._bridge = bridge_manager
        self._pos = positioning_service
        self._history = history_service
        self._mapper = floor_plan_mapper
        self._mqtt = mqtt_client
        self._alert = alert_service
        self._flush_interval = flush_interval
        self._stop = threading.Event()

        # SSE clients: set of queue.Queue instances to push to
        self._sse_queues: Set[object] = set()
        self._sse_lock = threading.Lock()

        # Tracker DB cache: hardware_id → tracker DB id
        self._tracker_cache: Dict[str, int] = {}
        self._cache_loaded = False

        # Per-tracker Kalman for velocity (tied to history service)
        self._prev_positions: Dict[str, Dict] = {}

    # ── SSE client management ──────────────────────────────────────────────────

    def register_sse_client(self, queue: object):
        with self._sse_lock:
            self._sse_queues.add(queue)
            logger.debug(f"SSE client registered (total: {len(self._sse_queues)})")

    def unregister_sse_client(self, queue: object):
        with self.sse_lock:
            self._sse_queues.discard(queue)
            logger.debug(f"SSE client unregistered (total: {len(self._sse_queues)})")

    @property
    def sse_lock(self):
        return self._sse_lock

    # ── Tracker cache ─────────────────────────────────────────────────────────

    def _ensure_cache(self):
        if self._cache_loaded:
            return
        with self._app.app_context():
            from backend.models import Tracker
            try:
                rows = Tracker.query.all()
                for t in rows:
                    self._tracker_cache[t.hardware_id] = t.id
                logger.info(f"Loaded {len(self._tracker_cache)} trackers into ingestion cache")
            except Exception as e:
                logger.error(f"Failed to load tracker cache: {e}")
        self._cache_loaded = True

    def _get_tracker_id(self, hardware_id: str) -> Optional[int]:
        """Map hardware_id → DB tracker id. Creates a Tracker if missing."""
        if hardware_id in self._tracker_cache:
            return self._tracker_cache[hardware_id]

        with self._app.app_context():
            from backend.models import Tracker
            from backend.extensions import db
            try:
                tracker = Tracker.query.filter_by(hardware_id=hardware_id).first()
                if not tracker:
                    # Auto-create tracker for unknown hardware
                    tracker = Tracker(
                        hardware_id=hardware_id,
                        name=f"Auto-{hardware_id[:12]}",
                        category="auto_discovered",
                    )
                    db.session.add(tracker)
                    db.session.commit()
                    logger.info(f"Auto-created tracker for hardware_id={hardware_id}")
                self._tracker_cache[hardware_id] = tracker.id
                return tracker.id
            except Exception as e:
                logger.error(f"Tracker cache error for {hardware_id}: {e}")
                return None

    # ── Main loop ──────────────────────────────────────────────────────────────

    def run(self):
        logger.info("IngestionLoop started")
        self._ensure_cache()

        while not self._stop.is_set():
            try:
                event = self._bridge.event_queue.get(timeout=0.5)
            except Exception:   # queue.Empty
                continue

            try:
                self._process_event(event)
            except Exception as e:
                logger.error(f"Ingestion processing error: {e}")

    def _process_event(self, event: Dict):
        tracker_hardware_id = event.get("tracker_hardware_id", "unknown")
        source = event.get("source", "UWB")
        payload = event.get("payload", {})
        hardware_name = event.get("hardware_name", "")
        timestamp = event.get("timestamp", datetime.now(timezone.utc))

        # Step 1: Position calculation
        pos_result = self._pos.position_from_payload(tracker_hardware_id, payload, source=source)
        if not pos_result:
            return  # Can't trilaterate with insufficient anchors / RSSI

        x, y, z = pos_result["x"], pos_result["y"], pos_result["z"]
        accuracy = pos_result.get("accuracy")

        # Step 2: Get tracker DB id
        tracker_id = self._get_tracker_id(tracker_hardware_id)
        if not tracker_id:
            return

        # Step 3: Write to history (batch buffered — returns immediately)
        self._history.write_position(
            tracker_id=tracker_id,
            x=x, y=y, z=z,
            accuracy=accuracy,
            source=source,
            hardware_id=tracker_hardware_id,
            timestamp=timestamp,
        )

        # Step 4: Evaluate alert conditions
        if self._alert:
            battery = payload.get("battery")
            env_data = payload.get("env") or payload.get("sensors")
            try:
                self._alert.evaluate_position(
                    tracker_id=tracker_id,
                    x=x, y=y, z=z,
                    hardware_id=tracker_hardware_id,
                    battery=battery,
                    env_data=env_data,
                )
            except Exception as e:
                logger.error(f"Alert evaluation error: {e}")

        # Step 5: Velocity from consecutive positions
        vx, vy, speed = None, None, None
        key = f"{tracker_id}"
        if key in self._prev_positions:
            prev = self._prev_positions[key]
            dt = (timestamp - prev["timestamp"]).total_seconds()
            if dt > 0 and dt < 10:  # Sanity: max gap 10s
                vx = round((x - prev["x"]) / dt, 3)
                vy = round((y - prev["y"]) / dt, 3)
                speed = round((vx**2 + vy**2)**0.5, 3)

        self._prev_positions[key] = {"x": x, "y": y, "z": z, "timestamp": timestamp}

        # Step 6: Build SSE payload
        sse_data = {
            "type": "position_update",
            "tracker_id": tracker_id,
            "hardware_id": tracker_hardware_id,
            "x": round(x, 3),
            "y": round(y, 3),
            "z": round(z, 3),
            "accuracy": round(accuracy, 3) if accuracy else None,
            "vx": vx,
            "vy": vy,
            "speed": speed,
            "source": source,
            "hardware_name": hardware_name,
            "timestamp": timestamp.isoformat(),
        }

        # Step 7: Broadcast to SSE clients
        self._broadcast_sse(sse_data)

        # Step 8: Publish to MQTT
        if self._mqtt and self._mqtt.is_connected():
            try:
                self._mqtt.publish("rtls/state_changes", json.dumps(sse_data), qos=1)
            except Exception as e:
                logger.error(f"MQTT publish error: {e}")

    def _broadcast_sse(self, data: Dict):
        """Push SSE event to all connected clients."""
        message = f"data: {json.dumps(data)}\n\n"
        with self._sse_lock:
            dead = set()
            for q in self._sse_queues:
                try:
                    q.put_nowait(message)
                except Exception:
                    dead.add(q)
            for q in dead:
                self._sse_queues.discard(q)

    def stop(self):
        self._stop.set()
        self.join(timeout=5)
        logger.info("IngestionLoop stopped")


# ── Global ingestion loop instance ────────────────────────────────────────────
_ingestion_loop: Optional[IngestionLoop] = None


def get_ingestion_loop() -> Optional[IngestionLoop]:
    return _ingestion_loop


def start_ingestion(app: Flask,
                     bridge_manager,
                     positioning_service,
                     history_service,
                     floor_plan_mapper,
                     mqtt_client=None,
                     alert_service=None):
    global _ingestion_loop
    if _ingestion_loop is not None and _ingestion_loop.is_alive():
        logger.warning("IngestionLoop already running")
        return _ingestion_loop

    _ingestion_loop = IngestionLoop(
        app=app,
        bridge_manager=bridge_manager,
        positioning_service=positioning_service,
        history_service=history_service,
        floor_plan_mapper=floor_plan_mapper,
        mqtt_client=mqtt_client,
        alert_service=alert_service,
    )
    _ingestion_loop.start()
    return _ingestion_loop
