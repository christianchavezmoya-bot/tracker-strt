"""HTTP client for BlueApro 6/6E / BlueUp TinyGateway vendor firmware."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth

from node_reader.tag_classifier import classify_scan_type, parse_eddystone, parse_ibeacon


@dataclass
class NodeDevice:
    mac: str
    name: str = ""
    rssi: int = -999
    scan_type: str = "UNKNOWN_BLE"
    raw: dict | None = None
    source: str = "node"


@dataclass
class NodeHealth:
    ok: bool
    message: str
    detail: str = ""
    info: dict | None = None


class _SourceIPAdapter(HTTPAdapter):
    """Bind outbound HTTP to a specific PC interface IP."""

    def __init__(self, source_ip: str, **kwargs):
        self._source_ip = source_ip
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["source_address"] = (self._source_ip, 0)
        return super().init_poolmanager(*args, **kwargs)


class BlueAproClient:
    """Pull tag data from BlueApro node over HTTP (vendor firmware)."""

    MODEL = "BlueApro 6/6E"
    DEFAULT_AP_IP = "192.168.4.1"
    FALLBACK_DEVICE_PATHS = (
        "/api/ble/devices",
        "/api/beacon/devices",
        "/api/scanner/devices",
        "/api/ble/scanner/devices",
        "/api/tags",
    )
    FALLBACK_HEALTH_PATHS = ("/api/system", "/api/system/info", "/")

    def __init__(
        self,
        host: str,
        port: int = 80,
        use_https: bool = False,
        username: str = "admin",
        password: str = "",
        devices_path: str = "/api/ble/devices",
        health_path: str = "/api/system",
        scan_start_path: str = "/api/ble/scanner/start",
        scan_stop_path: str = "/api/ble/scanner/stop",
        timeout: float = 8.0,
        source_ip: str | None = None,
    ):
        self.host = host.strip()
        self.port = int(port)
        self.use_https = use_https
        self.username = username
        self.password = password
        self.devices_path = devices_path
        self.health_path = health_path
        self.scan_start_path = scan_start_path
        self.scan_stop_path = scan_stop_path
        self.timeout = timeout
        self.source_ip = source_ip
        self._session = requests.Session()
        if source_ip:
            adapter = _SourceIPAdapter(source_ip)
            self._session.mount("http://", adapter)
            self._session.mount("https://", adapter)
        if username or password:
            self._session.auth = HTTPBasicAuth(username, password or "")

    @property
    def base_url(self) -> str:
        scheme = "https" if self.use_https else "http"
        if (self.use_https and self.port == 443) or (not self.use_https and self.port == 80):
            return f"{scheme}://{self.host}"
        return f"{scheme}://{self.host}:{self.port}"

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def test_connection(self) -> NodeHealth:
        paths = [self.health_path] + [p for p in self.FALLBACK_HEALTH_PATHS if p != self.health_path]
        last_err = ""
        for path in paths:
            try:
                r = self._session.get(self._url(path), timeout=self.timeout)
                if r.status_code == 401:
                    return NodeHealth(False, "Authentication failed", "Check node username/password")
                if r.status_code < 500:
                    info = {}
                    try:
                        if r.headers.get("content-type", "").startswith("application/json"):
                            info = r.json()
                    except Exception:
                        info = {"body": r.text[:200]}
                    return NodeHealth(True, f"Node reachable ({path})", detail=str(info)[:300], info=info if isinstance(info, dict) else None)
                last_err = f"HTTP {r.status_code}"
            except requests.RequestException as e:
                last_err = str(e)
        return NodeHealth(False, "Cannot reach BlueApro node", last_err)

    def fetch_devices(self) -> tuple[list[NodeDevice], str]:
        paths = [self.devices_path] + [p for p in self.FALLBACK_DEVICE_PATHS if p != self.devices_path]
        last_err = ""
        for path in paths:
            try:
                r = self._session.get(self._url(path), timeout=self.timeout)
                if r.status_code == 404:
                    last_err = f"{path} not found"
                    continue
                if r.status_code == 401:
                    return [], "Node authentication failed — check password"
                if r.status_code >= 400:
                    last_err = f"{path} HTTP {r.status_code}"
                    continue
                devices = parse_device_payload(r.text, r.headers.get("content-type", ""))
                if devices:
                    return devices, ""
                last_err = f"{path} returned no devices"
            except requests.RequestException as e:
                last_err = str(e)
        return [], last_err or "No device endpoint responded"

    def start_scan(self) -> NodeHealth:
        return self._post_action(self.scan_start_path, "Scan start requested")

    def stop_scan(self) -> NodeHealth:
        return self._post_action(self.scan_stop_path, "Scan stop requested")

    def _post_action(self, path: str, ok_msg: str) -> NodeHealth:
        try:
            r = self._session.post(self._url(path), json={}, timeout=self.timeout)
            if r.status_code in (200, 201, 204):
                return NodeHealth(True, ok_msg)
            if r.status_code == 404:
                return NodeHealth(True, f"{ok_msg} (endpoint not on firmware — scan may already run)")
            return NodeHealth(False, f"HTTP {r.status_code}", r.text[:200])
        except requests.RequestException as e:
            return NodeHealth(False, "Request failed", str(e))


def _norm_mac(mac: str) -> str:
    mac = re.sub(r"[^0-9a-fA-F]", "", mac or "")
    if len(mac) != 12:
        return (mac or "").upper()
    return ":".join(mac[i : i + 2] for i in range(0, 12, 2)).upper()


def parse_device_payload(body: str, content_type: str = "") -> list[NodeDevice]:
    """Parse BlueUp / BlueApro JSON, CSV, or HOLO-style payloads."""
    body = (body or "").strip()
    if not body:
        return []

    if "json" in content_type or body.startswith(("{", "[")):
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return _parse_csv_lines(body)
        return _parse_json_devices(data)

    return _parse_csv_lines(body)


def _parse_json_devices(data: Any) -> list[NodeDevice]:
    items: list[Any]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("devices", "items", "tags", "beacons", "data", "results", "ble_devices"):
            if isinstance(data.get(key), list):
                items = data[key]
                break
        else:
            items = [data]
    else:
        return []

    out: list[NodeDevice] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        mac = _norm_mac(
            str(
                item.get("mac")
                or item.get("mac_address")
                or item.get("address")
                or item.get("bdaddr")
                or ""
            )
        )
        if not mac or mac in seen:
            continue
        seen.add(mac)
        name = str(item.get("name") or item.get("local_name") or item.get("adv_name") or "")
        rssi = item.get("rssi")
        if rssi is None:
            rssi = item.get("RSSI", item.get("signal", -999))
        try:
            rssi = int(rssi)
        except (TypeError, ValueError):
            rssi = -999
        adv_hex = item.get("payload") or item.get("adv_data") or item.get("data")
        ib = ed = None
        if isinstance(adv_hex, str) and len(adv_hex) >= 4:
            try:
                raw = bytes.fromhex(adv_hex.replace(":", ""))
                ib = parse_ibeacon({0x004C: raw}) if raw else None
            except Exception:
                pass
        st = classify_scan_type(name, ib, ed, [])
        out.append(NodeDevice(mac=mac, name=name, rssi=rssi, scan_type=st, raw=item, source="node"))
    return out


def _parse_csv_lines(body: str) -> list[NodeDevice]:
    out: list[NodeDevice] = []
    for line in body.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        # NodeMAC, TagMAC, RSSI, Battery
        mac = _norm_mac(parts[1] if len(parts) >= 3 else parts[0])
        if not mac:
            continue
        try:
            rssi = int(float(parts[2] if len(parts) >= 3 else parts[1]))
        except ValueError:
            rssi = -999
        out.append(NodeDevice(mac=mac, rssi=rssi, source="node"))
    return out


def parse_push_payload(body: bytes, content_type: str = "") -> list[NodeDevice]:
    """Parse HTTP POST body from BlueApro when gateway pushes scan data."""
    text = body.decode("utf-8", errors="replace")
    devices = parse_device_payload(text, content_type)
    if devices:
        for d in devices:
            d.source = "node-push"
        return devices
    # BlueUp compact JSON lines
    out: list[NodeDevice] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            out.extend(_parse_json_devices(obj if isinstance(obj, list) else [obj]))
        except json.JSONDecodeError:
            continue
    for d in out:
        d.source = "node-push"
    return out
