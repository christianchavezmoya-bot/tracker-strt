"""HTTP and MQTT transport to HOLO-RTLS server."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urljoin

import requests

LogFn = Callable[[str, str, str], None]  # direction, channel, message


@dataclass
class ConnectionResult:
    ok: bool
    message: str
    detail: str = ""


class ServerTransport:
    """Mixed HTTP + MQTT uplink for scanner detections."""

    def __init__(self, log: LogFn | None = None):
        self.log = log or (lambda _d, _c, _m: None)
        self._mqtt_client = None
        self._mqtt_thread = None
        self._connected = False
        self._transport = "http"
        self._jwt: str | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def jwt(self) -> str | None:
        return self._jwt

    def base_url(self, host: str, port: int) -> str:
        return f"http://{host}:{port}"

    def login(self, host: str, port: int, email: str, password: str) -> ConnectionResult:
        url = f"{self.base_url(host, port)}/api/auth/login"
        try:
            r = requests.post(url, json={"email": email, "password": password}, timeout=8)
            self.log("OUT", "HTTP", f"POST /api/auth/login → {r.status_code}")
            if r.status_code != 200:
                return ConnectionResult(False, "Login failed", r.text[:200])
            data = r.json()
            self._jwt = data.get("access_token")
            return ConnectionResult(True, "Logged in")
        except requests.RequestException as e:
            return ConnectionResult(False, "Login error", str(e))

    def fetch_nodes(self, host: str, port: int) -> tuple[list[dict], str]:
        if not self._jwt:
            return [], "Not logged in — enter admin email/password and connect"
        url = f"{self.base_url(host, port)}/api/nodes"
        try:
            r = requests.get(url, headers={"Authorization": f"Bearer {self._jwt}"}, timeout=8)
            self.log("IN", "HTTP", f"GET /api/nodes → {r.status_code}")
            if r.status_code != 200:
                return [], r.text[:200]
            return r.json().get("items", []), ""
        except requests.RequestException as e:
            return [], str(e)

    def test_http(self, host: str, port: int, api_key: str) -> ConnectionResult:
        url = f"{self.base_url(host, port)}/api/scanner/detections"
        payload = {"anchor_mac": "00:00:00:00:00:00", "detections": []}
        try:
            r = requests.post(
                url,
                json=payload,
                headers={"X-Scanner-Key": api_key, "Content-Type": "application/json"},
                timeout=8,
            )
            self.log("OUT", "HTTP", f"POST /api/scanner/detections (test) → {r.status_code}")
            if r.status_code in (200, 201, 400):
                return ConnectionResult(True, "HTTP scanner endpoint reachable")
            if r.status_code == 401:
                return ConnectionResult(False, "Scanner API key rejected", r.text[:200])
            return ConnectionResult(False, f"HTTP {r.status_code}", r.text[:200])
        except requests.RequestException as e:
            return ConnectionResult(False, "Cannot reach server", str(e))

    def connect(
        self,
        host: str,
        server_port: int,
        transport: str,
        mqtt_port: int,
        mqtt_tls: bool,
        mqtt_topic: str,
        mqtt_user: str = "",
        mqtt_pass: str = "",
        api_key: str = "",
    ) -> ConnectionResult:
        self.disconnect()
        self._transport = transport.lower()
        if self._transport == "http":
            res = self.test_http(host, server_port, api_key)
            self._connected = res.ok
            return res
        return self._connect_mqtt(host, mqtt_port, mqtt_tls, mqtt_topic, mqtt_user, mqtt_pass)

    def _connect_mqtt(
        self, host: str, port: int, tls: bool, topic: str, user: str, password: str
    ) -> ConnectionResult:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            return ConnectionResult(False, "paho-mqtt not installed", "pip install paho-mqtt")

        if tls and port == 1883:
            port = 8883

        connected_event = threading.Event()
        result = {"ok": False, "msg": ""}

        def on_connect(client, userdata, flags, rc, properties=None):
            if rc == 0:
                result["ok"] = True
                result["msg"] = "MQTT connected"
                client.subscribe("rtls/state_changes")
                client.subscribe("rtls/alarms/trigger")
                self.log("IN", "MQTT", f"Subscribed rtls/state_changes, rtls/alarms/trigger")
            else:
                result["msg"] = f"MQTT connect rc={rc}"
            connected_event.set()

        def on_message(client, userdata, msg):
            self.log("IN", "MQTT", f"{msg.topic}: {msg.payload.decode('utf-8', errors='replace')[:500]}")

        cid = f"holo-node-reader-{int(time.time())}"
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)
        if user:
            client.username_pw_set(user, password or "")
        if tls:
            client.tls_set()
        client.on_connect = on_connect
        client.on_message = on_message
        try:
            client.connect(host, port, keepalive=30)
        except Exception as e:
            return ConnectionResult(False, "MQTT connect failed", str(e))
        client.loop_start()
        connected_event.wait(timeout=6)
        if not result["ok"]:
            client.loop_stop()
            return ConnectionResult(False, result["msg"] or "MQTT timeout")
        self._mqtt_client = client
        self._mqtt_topic = topic
        self._connected = True
        self.log("OUT", "MQTT", f"Connected to {host}:{port} topic={topic}")
        return ConnectionResult(True, result["msg"])

    def disconnect(self) -> None:
        self._connected = False
        if self._mqtt_client:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception:
                pass
            self._mqtt_client = None

    def send_detections(
        self,
        host: str,
        server_port: int,
        api_key: str,
        anchor_mac: str,
        detections: list[dict],
    ) -> ConnectionResult:
        if not detections:
            return ConnectionResult(True, "No detections")
        if self._transport == "mqtt" and self._mqtt_client:
            return self._publish_mqtt(anchor_mac, detections)
        return self._post_http(host, server_port, api_key, anchor_mac, detections)

    def _post_http(
        self, host: str, port: int, api_key: str, anchor_mac: str, detections: list[dict]
    ) -> ConnectionResult:
        url = f"{self.base_url(host, port)}/api/scanner/detections"
        payload = {"anchor_mac": anchor_mac.upper(), "detections": detections}
        try:
            r = requests.post(
                url,
                json=payload,
                headers={"X-Scanner-Key": api_key, "Content-Type": "application/json"},
                timeout=8,
            )
            self.log("OUT", "HTTP", f"POST detections ({len(detections)}) → {r.status_code}")
            if r.status_code in (200, 201):
                return ConnectionResult(True, "Sent")
            return ConnectionResult(False, f"HTTP {r.status_code}", r.text[:200])
        except requests.RequestException as e:
            return ConnectionResult(False, "Send failed", str(e))

    def _publish_mqtt(self, anchor_mac: str, detections: list[dict]) -> ConnectionResult:
        if not self._mqtt_client:
            return ConnectionResult(False, "MQTT not connected")
        topic = getattr(self, "_mqtt_topic", "rssi/data")
        try:
            for d in detections:
                line = f"{anchor_mac},{d['mac_address']},{d['rssi']},100"
                self._mqtt_client.publish(topic, line, qos=1)
                self.log("OUT", "MQTT", f"PUBLISH {topic}: {line}")
            return ConnectionResult(True, f"Published {len(detections)}")
        except Exception as e:
            return ConnectionResult(False, "MQTT publish failed", str(e))


def scan_network_for_servers(port: int = 5000, timeout: float = 0.35) -> list[str]:
    """Quick scan of /24 subnet for HOLO-RTLS HTTP port."""
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except OSError:
        return []

    prefix = ".".join(local_ip.split(".")[:3])
    found: list[str] = []
    threads: list[threading.Thread] = []

    def probe(ip: str) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            if sock.connect_ex((ip, port)) == 0:
                found.append(ip)
            sock.close()
        except OSError:
            pass

    for i in range(1, 255):
        ip = f"{prefix}.{i}"
        t = threading.Thread(target=probe, args=(ip,), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=timeout + 0.1)
    return sorted(set(found))
