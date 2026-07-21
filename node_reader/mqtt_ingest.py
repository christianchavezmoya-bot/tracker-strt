"""MQTT subscriber — receive BLE tag data from WiFi unit broker (port 1883)."""
from __future__ import annotations

import threading
import time
from typing import Callable

from node_reader.mqtt_parse import parse_mqtt_payload

LogFn = Callable[[str, str, str], None]
OnDevices = Callable[[list], None]

DEFAULT_PORT = 1883
DEFAULT_TOPICS = ("rssi/data", "rssi/raw", "ble/rssi", "wifi/rssi")

BLUEAPRO_MQTT_HINT = (
    "WiFi unit publishes tags to its MQTT broker (port {port}).\n"
    "  Broker host = node IP below (e.g. 192.168.1.1)\n"
    "  Topics: {topics}\n"
    "  Payload CSV: NodeMAC,TagMAC,RSSI,Battery\n"
    "PC subscribes — allow outbound TCP {port} to the node (no PC inbound rule)."
)


class MqttIngestClient:
    """Subscribe to gateway MQTT broker and parse incoming tag messages."""

    def __init__(
        self,
        host: str = "192.168.1.1",
        port: int = DEFAULT_PORT,
        topics: list[str] | None = None,
        username: str = "",
        password: str = "",
        tls: bool = False,
        on_devices: OnDevices | None = None,
        log: LogFn | None = None,
    ):
        self.host = host.strip()
        self.port = int(port)
        self.topics = [t.strip() for t in (topics or list(DEFAULT_TOPICS)) if t.strip()]
        self.username = username
        self.password = password
        self.tls = tls
        self.on_devices = on_devices
        self.log = log or (lambda _d, _c, _m: None)
        self._client = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.message_count = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> tuple[bool, str]:
        if self.running:
            return True, f"MQTT already connected to {self.host}:{self.port}"
        if not self.host:
            return False, "MQTT broker host is empty — set Node / broker IP"
        self._stop.clear()
        connected = threading.Event()
        result: dict = {"ok": False, "msg": ""}

        def run() -> None:
            try:
                import paho.mqtt.client as mqtt
            except ImportError:
                result["msg"] = "paho-mqtt not installed — pip install paho-mqtt"
                connected.set()
                return

            def on_connect(client, userdata, flags, reason_code, properties=None):
                if reason_code == 0:
                    for topic in self.topics:
                        client.subscribe(topic)
                        self.log("OUT", "MQTT", f"Subscribe {topic}")
                    result["ok"] = True
                    result["msg"] = f"MQTT connected {self.host}:{self.port} ({len(self.topics)} topic(s))"
                    self.log("OUT", "MQTT", result["msg"])
                else:
                    result["msg"] = f"MQTT connect failed rc={reason_code}"
                    self.log("IN", "MQTT", result["msg"])
                connected.set()

            def on_message(client, userdata, msg):
                if self._stop.is_set():
                    return
                text = msg.payload.decode("utf-8", errors="replace")
                self.message_count += 1
                preview = text[:120].replace("\n", " ")
                self.log("IN", "MQTT", f"{msg.topic}: {preview}")
                devices = parse_mqtt_payload(text, msg.topic)
                if self.on_devices and devices:
                    self.on_devices(devices)

            cid = f"holo-node-reader-{int(time.time())}"
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)
            if self.username:
                client.username_pw_set(self.username, self.password or "")
            if self.tls:
                client.tls_set()
            client.on_connect = on_connect
            client.on_message = on_message
            self._client = client
            try:
                client.connect(self.host, self.port, keepalive=30)
            except OSError as e:
                result["msg"] = f"MQTT connect error: {e}"
                self.log("IN", "MQTT", result["msg"])
                connected.set()
                return
            client.loop_start()
            while not self._stop.is_set():
                time.sleep(0.5)
            client.loop_stop()
            try:
                client.disconnect()
            except OSError:
                pass
            self._client = None

        self._thread = threading.Thread(target=run, daemon=True, name="MqttIngest")
        self._thread.start()
        connected.wait(timeout=10)
        if not result["ok"]:
            self.stop()
            return False, result.get("msg") or "MQTT connection timeout — check broker IP and port 1883"
        return True, result["msg"]

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=4)
            self._thread = None
        self._client = None
