"""
HOLO-RTLS — Hardware Bridge Service
Wraps reference/uwb_serial_reader.py and provides an MQTT client.
Unified interface: HardwareBridge.start_all() starts everything from DB config.
"""
from __future__ import annotations
import json
import logging
import threading
import queue
import time
from datetime import datetime, timezone
from typing import Dict, Callable, Optional

import sys, os
_ref_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "reference")
if _ref_path not in sys.path:
    sys.path.insert(0, _ref_path)

from uwb_serial_reader import UWBSerialReader

logger = logging.getLogger(__name__)


# ── Events emitted by hardware bridges ────────────────────────────────────────
#
# Every bridge pushes messages to self.event_queue with shape:
# {
#   "tracker_hardware_id": str,
#   "hardware_config_id": int,
#   "source": "UWB" | "BLE" | "WIFI" | "ENVIRO" | "SEWIO",
#   "payload": {...},          # raw hardware payload
#   "hardware_name": str,
#   "timestamp": datetime,
# }
#
# Consumers pull from event_queue and pass to the PositioningService.


class SerialBridge(threading.Thread):
    """
    Reads UWB range data from a serial port.
    Runs in its own thread; pushes events to event_queue.
    """

    def __init__(self, config_id: int, config_name: str,
                 port: str, baudrate: int,
                 format_type: str, tracker_id_field: str,
                 event_queue: queue.Queue, app_context=None):
        super().__init__(daemon=True, name=f"SerialBridge-{config_name}")
        self.config_id = config_id
        self.config_name = config_name
        self.port = port
        self.baudrate = baudrate
        self.format_type = format_type or "auto"
        self.tracker_id_field = tracker_id_field or "tag_id"
        self._queue = event_queue
        self._app = app_context
        self._stop = threading.Event()
        self._reader: Optional[UWBSerialReader] = None

    def _on_ranges(self, ranges: Dict[str, float]):
        """Called by UWBSerialReader when it has parsed ranges."""
        msg = {
            "tracker_hardware_id": "serial_tag",      # overridden if payload has tag_id
            "hardware_config_id": self.config_id,
            "source": "UWB",
            "payload": ranges,
            "hardware_name": self.config_name,
            "timestamp": datetime.now(timezone.utc),
        }
        # Try to extract tracker ID from ranges if present
        if self.tracker_id_field in ranges:
            msg["tracker_hardware_id"] = str(ranges.pop(self.tracker_id_field))
        self._queue.put(msg)

    def run(self):
        try:
            self._reader = UWBSerialReader(port=self.port, baudrate=self.baudrate)
            if not self._reader.connect():
                logger.error(f"[{self.name}] Failed to open {self.port}")
                return

            self._reader.set_callback(self._on_ranges)
            logger.info(f"[{self.name}] Started reading {self.port}@{self.baudrate}")

            while not self._stop.is_set():
                line = self._reader.read_line()
                if line:
                    self._reader.parse_dwm1001_format(line)
                time.sleep(0.01)

        except Exception as e:
            logger.error(f"[{self.name}] Error: {e}")
        finally:
            if self._reader:
                self._reader.disconnect()

    def stop(self):
        self._stop.set()
        self.join(timeout=3)


class MockBridge(threading.Thread):
    """
    Generates synthetic position data for testing / demo.
    No real hardware needed.
    """

    def __init__(self, config_id: int, config_name: str,
                 anchors: Dict[str, tuple],
                 interval: float = 0.5,
                 event_queue: queue.Queue,
                 tracker_ids: list = None):
        super().__init__(daemon=True, name=f"MockBridge-{config_name}")
        self.config_id = config_id
        self.config_name = config_name
        self._anchors = anchors
        self._interval = interval
        self._queue = event_queue
        self._stop = threading.Event()
        self._tracker_ids = tracker_ids or ["TAG_001", "TAG_002", "TAG_003"]

    def run(self):
        import random, math, numpy as np

        logger.info(f"[{self.name}] Starting mock data generator")
        t = 0.0
        while not self._stop.is_set():
            t += self._interval
            for tag_id in self._tracker_ids:
                # Lissajous-style movement for demo
                x = 5.0 + 2.0 * math.sin(t * 0.3 + hash(tag_id) % 10)
                y = 3.0 + 1.5 * math.cos(t * 0.5 + hash(tag_id) % 7)

                ranges = {}
                for anchor_id, (ax, ay, az) in self._anchors.items():
                    dist = math.sqrt((x - ax) ** 2 + (y - ay) ** 2)
                    ranges[anchor_id] = max(0.1, dist + random.gauss(0, 0.05))

                self._queue.put({
                    "tracker_hardware_id": tag_id,
                    "hardware_config_id": self.config_id,
                    "source": "UWB",
                    "payload": ranges,
                    "hardware_name": self.config_name,
                    "timestamp": datetime.now(timezone.utc),
                })

            time.sleep(self._interval)

    def stop(self):
        self._stop.set()
        self.join(timeout=2)


class MQTTSubscriber(threading.Thread):
    """
    Subscribes to MQTT topics and pushes events to event_queue.
    Topics: rssi/data, vitals/data, env/data (configurable per config).
    """

    def __init__(self, config_id: int, config_name: str,
                 broker_host: str, broker_port: int,
                 username: str, password: str,
                 topics: list,
                 field_mapping: dict,
                 event_queue: queue.Queue):
        super().__init__(daemon=True, name=f"MQTTSubscriber-{config_name}")
        self.config_id = config_id
        self.config_name = config_name
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self.topics = topics or ["rssi/data", "rssi/raw"]
        self.field_mapping = field_mapping or {}   # Maps device payload → HOLO-RTLS fields
        self._queue = event_queue
        self._stop = threading.Event()
        self._client = None
        self._paho = None

    def _build_paho(self):
        try:
            import paho.mqtt.client as mqtt
            self._paho = mqtt
            return True
        except ImportError:
            logger.warning("paho-mqtt not installed — MQTT unavailable")
            return False

    def _on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode("utf-8"))

            # Determine source from topic
            source = "SEWIO"
            if "rssi" in topic or "ble" in topic:
                source = "BLE"
            elif "wifi" in topic:
                source = "WIFI"
            elif "env" in topic or "sensors" in topic:
                source = "ENVIRO"

            # Extract tracker hardware ID from field_mapping or payload
            tag_id = self.field_mapping.get("tag_id", "tag_id")
            tracker_hardware_id = str(payload.get(tag_id, "unknown"))

            # Apply field mapping (rename keys)
            mapped = {}
            for rtls_key, device_key in self.field_mapping.items():
                if device_key in payload:
                    mapped[rtls_key] = payload[device_key]
            if not mapped:
                mapped = payload  # Fall back to raw payload

            self._queue.put({
                "tracker_hardware_id": tracker_hardware_id,
                "hardware_config_id": self.config_id,
                "source": source,
                "payload": mapped,
                "hardware_name": self.config_name,
                "timestamp": datetime.now(timezone.utc),
            })
        except Exception as e:
            logger.error(f"[{self.name}] MQTT parse error: {e}")

    def run(self):
        if not self._build_paho():
            return

        client = self._paho.Client()
        if self.username:
            client.username_pw_set(self.username, self.password or "")
        client.on_message = self._on_message

        try:
            logger.info(f"[{self.name}] Connecting to {self.broker_host}:{self.broker_port}")
            client.connect(self.broker_host, self.broker_port, keepalive=30)
            for topic in self.topics:
                client.subscribe(topic)
                logger.info(f"[{self.name}] Subscribed to {topic}")
            client.loop_start()

            while not self._stop.is_set():
                time.sleep(1)
                # Heartbeat: check client is still connected
                if not client.is_connected():
                    logger.warning(f"[{self.name}] MQTT disconnected — reconnecting")
                    client.reconnect()

        except Exception as e:
            logger.error(f"[{self.name}] MQTT error: {e}")
        finally:
            client.loop_stop()
            client.disconnect()

    def stop(self):
        self._stop.set()
        self.join(timeout=3)


# ── Hardware Bridge Manager ────────────────────────────────────────────────────
# Starts/stops bridges based on active HardwareConfig rows in the DB.

class HardwareBridgeManager:
    """
    Reads active HardwareConfig rows from the DB and starts the appropriate
    bridge (serial or MQTT) for each. Runs all bridges in background threads.
    """

    def __init__(self, db_session, app=None):
        self._db = db_session
        self._app = app
        self._bridges: Dict[int, threading.Thread] = {}   # config_id → thread
        self._queue: queue.Queue = queue.Queue(maxsize=10000)
        self._running = False
        self._lock = threading.Lock()

    @property
    def event_queue(self) -> queue.Queue:
        """Ingestion loop consumes from this queue."""
        return self._queue

    def start_all(self, anchors: Dict[str, tuple] = None):
        """
        Read all active HardwareConfig rows and start bridges.
        Call after app is initialised, e.g. in app factory.
        """
        from backend.models import HardwareConfig
        from backend.models.hardware import ConnectionStatus

        if self._running:
            logger.warning("Bridge manager already running")
            return

        configs = self._db.query(HardwareConfig).filter(
            HardwareConfig.is_active == True,
            HardwareConfig.status.in_([ConnectionStatus.CONNECTED, ConnectionStatus.DISCONNECTED])
        ).all()

        logger.info(f"Starting {len(configs)} hardware bridges...")
        for cfg in configs:
            self._start_bridge(cfg, anchors)

        self._running = True

    def _start_bridge(self, cfg, anchors: Dict[str, tuple] = None):
        from backend.models.hardware import Protocol, ConnectionStatus
        from backend.models.hardware_profiles import get_profile

        profile = get_profile(cfg.profile_id)
        settings = cfg.get_settings()

        try:
            bridge = None
            protocol = Protocol(cfg.protocol)

            if protocol == Protocol.SERIAL:
                bridge = SerialBridge(
                    config_id=cfg.id,
                    config_name=cfg.name,
                    port=settings.get("port", "/dev/ttyUSB0"),
                    baudrate=int(settings.get("baud_rate", 115200)),
                    format_type=settings.get("format_type", "dwm1001"),
                    tracker_id_field=settings.get("tracker_id_field", "tag_id"),
                    event_queue=self._queue,
                )

            elif protocol == Protocol.MQTT:
                bridge = MQTTSubscriber(
                    config_id=cfg.id,
                    config_name=cfg.name,
                    broker_host=settings.get("broker_host", "localhost"),
                    broker_port=int(settings.get("broker_port", 1883)),
                    username=settings.get("username", ""),
                    password=settings.get("password", ""),
                    topics=settings.get("topics", ["rssi/data", "rssi/raw"]).split(","),
                    field_mapping=settings.get("field_mapping", {}),
                    event_queue=self._queue,
                )

            elif profile and profile.id == "mock_data":
                bridge = MockBridge(
                    config_id=cfg.id,
                    config_name=cfg.name,
                    anchors=anchors or {},
                    interval=float(settings.get("interval", 0.5)),
                    tracker_ids=settings.get("tracker_ids", "TAG_001,TAG_002,TAG_003").split(","),
                    event_queue=self._queue,
                )

            if bridge:
                bridge.start()
                self._bridges[cfg.id] = bridge
                cfg.status = ConnectionStatus.CONNECTED
                self._db.commit()
                logger.info(f"Started bridge for config {cfg.id}: {cfg.name}")
            else:
                logger.warning(f"No bridge for config {cfg.id} (protocol {protocol})")

        except Exception as e:
            logger.error(f"Failed to start bridge for config {cfg.id}: {e}")
            cfg.status = ConnectionStatus.ERROR
            cfg.error_message = str(e)
            self._db.commit()

    def stop_all(self):
        """Stop all bridges and wait for them to finish."""
        logger.info("Stopping all hardware bridges...")
        self._running = False
        for cfg_id, bridge in list(self._bridges.items()):
            try:
                bridge.stop()
            except Exception as e:
                logger.error(f"Error stopping bridge {cfg_id}: {e}")
        self._bridges.clear()
        logger.info("All bridges stopped")

    def reload(self, anchors: Dict[str, tuple] = None):
        """Stop all, re-read DB, restart. Call after config changes."""
        self.stop_all()
        self.start_all(anchors)

    def queue_size(self) -> int:
        return self._queue.qsize()


# ── Singleton ─────────────────────────────────────────────────────────────────
_bridge_manager: Optional[HardwareBridgeManager] = None


def get_bridge_manager() -> HardwareBridgeManager:
    global _bridge_manager
    if _bridge_manager is None:
        from backend.extensions import db
        _bridge_manager = HardwareBridgeManager(db.session)
    return _bridge_manager
