"""
HOLO-RTLS — SSE / Stream API
Real-time position updates pushed to browsers via Server-Sent Events.
Also handles MQTT state sync publishing.
"""
from __future__ import annotations
import json
import logging
import queue
import threading
from datetime import datetime, timezone
from typing import Optional
from flask import (
    Blueprint, Response, stream_with_context,
    request, jsonify, current_app,
)
from flask_jwt_extended import jwt_required, get_jwt_identity

logger = logging.getLogger(__name__)
stream_bp = Blueprint("stream", __name__, url_prefix="/api/stream")


# ── MQTT publisher (outbound state_changes) ────────────────────────────────────

class MQTTPublisher:
    """
    Thin wrapper around paho-mqtt for the state_changes topic.
    Initialised once by the app factory.
    """
    def __init__(self):
        self._client = None
        self._connected = False

    def connect(self, host: str, port: int, username: str = None, password: str = None):
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.warning("paho-mqtt not installed — MQTT publishing disabled")
            return

        self._client = mqtt.Client()
        if username:
            self._client.username_pw_set(username, password or "")
        self._client.on_connect = lambda c, u, f, rc: setattr(self, "_connected", rc == 0)
        self._client.on_disconnect = lambda c, u, rc: setattr(self, "_connected", False)
        try:
            self._client.connect(host, port, keepalive=30)
            self._client.loop_start()
            logger.info(f"MQTT publisher connected to {host}:{port}")
        except Exception as e:
            logger.error(f"MQTT connect failed: {e}")

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    def publish(self, topic: str, payload: str, qos: int = 0):
        if self._client and self._connected:
            try:
                self._client.publish(topic, payload, qos=qos)
            except Exception as e:
                logger.error(f"MQTT publish error: {e}")

    def disconnect(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()


# ── SSE endpoint ───────────────────────────────────────────────────────────────

@stream_bp.route("/positions")
@jwt_required()
def positions_stream():
    """
    Server-Sent Events stream — pushes live position updates.

    Event types sent:
      position_update  — new position for a tracker
      heartbeat        — keepalive every 15s
      alert            — alert triggered
      system_status    — periodic status update

    Browser usage:
      const es = new EventSource('/api/stream/positions');
      es.addEventListener('position_update', e => {
        const data = JSON.parse(e.data);
        // data = { tracker_id, x, y, z, accuracy, vx, vy, speed, source, timestamp }
      });
    """
    user_id = get_jwt_identity()

    # Get or create the ingestion loop
    from backend.services.ingestion_loop import get_ingestion_loop
    loop = get_ingestion_loop()

    # Create a dedicated queue for this client
    client_queue = queue.Queue(maxsize=200)

    if loop:
        loop.register_sse_client(client_queue)
        logger.info(f"SSE client {user_id} connected")
    else:
        logger.warning("IngestionLoop not running — SSE will send stale data only")

    def generate():
        try:
            # Send initial snapshot (last known positions)
            yield _snapshot_event()

            # Stream events
            while True:
                try:
                    msg = client_queue.get(timeout=30)
                    yield msg
                except queue.Empty:
                    # Keepalive heartbeat
                    yield f"data: {json.dumps({'type': 'heartbeat', 'ts': datetime.now(timezone.utc).isoformat()})}\n\n"

        except GeneratorExit:
            pass
        finally:
            if loop:
                loop.unregister_sse_client(client_queue)
            logger.info(f"SSE client {user_id} disconnected")

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # Disable nginx buffering
            "Access-Control-Allow-Origin": "*",
        },
    )


def _snapshot_event() -> str:
    """Send current position snapshot for all trackers on connect."""
    from backend.models.positioning import PositionSnapshot
    from backend.models import Tracker
    from backend.extensions import db

    try:
        snapshots = db.session.query(PositionSnapshot).all()
        items = [s.to_dict() for s in snapshots]
        # Fallback: include Tracker last known coords if snapshot empty
        if not items:
            for t in Tracker.query.all():
                if t.pos_x is None and t.pos_y is None:
                    continue
                items.append({
                    "tracker_id": t.id,
                    "hardware_id": t.hardware_id,
                    "x": t.pos_x or 0,
                    "y": t.pos_y or 0,
                    "z": t.pos_z or 0,
                    "source": "TRACKER",
                })
        return f"data: {json.dumps({'type': 'snapshot', 'positions': items})}\n\n"
    except Exception as e:
        logger.error(f"Error building snapshot: {e}")
        return f"data: {json.dumps({'type': 'snapshot', 'positions': []})}\n\n"


# ── Status endpoint ───────────────────────────────────────────────────────────

@stream_bp.route("/status")
@jwt_required()
def stream_status():
    """Return current stream health and connected client count."""
    from backend.services.ingestion_loop import get_ingestion_loop
    from backend.services.hardware_bridge import get_bridge_manager

    loop = get_ingestion_loop()
    bridge = get_bridge_manager()

    client_count = 0
    if loop and hasattr(loop, "_sse_queues"):
        with loop.sse_lock:
            client_count = len(loop._sse_queues)

    queue_depth = bridge.queue_size() if bridge else 0

    return jsonify({
        "ingestion_running": loop is not None and loop.is_alive(),
        "sse_clients": client_count,
        "queue_depth": queue_depth,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── Global MQTT publisher ─────────────────────────────────────────────────────
_mqtt_publisher: Optional[MQTTPublisher] = None


def get_mqtt_publisher() -> Optional[MQTTPublisher]:
    return _mqtt_publisher


def init_mqtt_publisher(host: str, port: int = 1883,
                        username: str = None, password: str = None):
    global _mqtt_publisher
    _mqtt_publisher = MQTTPublisher()
    _mqtt_publisher.connect(host, port, username, password)
    return _mqtt_publisher
