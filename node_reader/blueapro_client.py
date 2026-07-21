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
    device_type: str = "unknown"  # blueapro | openwrt | generic | unknown


def detect_host_type(body: str, content_type: str = "") -> str:
    """Guess whether HTTP response is from BlueApro, OpenWrt router, etc."""
    text = (body or "")[:8000].lower()
    if "openwrt" in text or "luci" in text or "cgi-bin/luci" in text:
        if any(k in text for k in ("strata", "ucentral", "ucentral.io")):
            return "openwrt_strata"
        return "openwrt"
    if any(k in text for k in ("blueup", "tinygateway", "blueapro", "blue beacon")):
        return "blueapro"
    if "json" in (content_type or "").lower():
        try:
            data = json.loads(body)
            if isinstance(data, dict) and any(k in data for k in ("devices", "ble", "gateway", "scanner")):
                return "blueapro"
        except json.JSONDecodeError:
            pass
    if "<html" in text:
        return "generic_web"
    return "unknown"


ROUTER_HINT = (
    "This host runs OpenWrt (LuCI admin) — not the BlueUp Transport UI.\n\n"
    "You will NOT find Transport / Encoding / Send realtime in LuCI Network menus.\n\n"
    "If this is BlueApro hardware with OpenWrt/STRATA firmware, BLE export must be "
    "configured elsewhere (Services tab, MQTT, SSH, or vendor portal).\n\n"
    "If the device also has BlueUp TinyGateway firmware, try:\n"
    "  • Wi-Fi AP: SSID TinyGateway / password tinygateway\n"
    "  • Browser: http://192.168.4.1  (login password: blueup)\n"
    "  • Configuration → Data transport/encoding → Raw UDP Client\n\n"
    "Do NOT use LuCI → System → Logging → External log server (syslog only, not tags)."
)

OPENWRT_STRATA_HINT = (
    "OpenWrt + STRATA/uCentral detected at this IP.\n\n"
    "This admin UI manages Wi-Fi/network — it does not stream BLE tags to UDP 8765.\n\n"
    "Next steps:\n"
    "1) LuCI → Services — look for BLE, MQTT, scanner, or STRATA apps\n"
    "2) Try BlueUp UI at http://192.168.4.1 (AP mode: SSID TinyGateway)\n"
    "3) Ask BlueApro vendor which firmware you have and how to export BLE scans\n"
    "4) If MQTT broker exists (port 1883), tags may publish to topic rssi/data"
)

PUSH_MODE_HINT = (
    "No BLE tag API on this host (all paths returned 404).\n"
    "BlueApro vendor firmware usually uses Push mode:\n"
    "  BlueApro web UI → Transport → HTTP → URI = http://YOUR_PC_IP:8765/ingest/blueapro"
)


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
        """Verify host is reachable AND looks like a BlueApro (or warn if router)."""
        # Prefer proving a BLE devices endpoint exists
        devices, dev_err = self.fetch_devices()
        if devices:
            return NodeHealth(
                True,
                f"BlueApro BLE API OK ({len(devices)} tag(s) visible)",
                device_type="blueapro",
            )

        paths = [self.health_path] + [p for p in self.FALLBACK_HEALTH_PATHS if p != self.health_path]
        last_err = dev_err or ""
        page_type = "unknown"
        for path in paths:
            try:
                r = self._session.get(self._url(path), timeout=self.timeout)
                if r.status_code == 401:
                    return NodeHealth(False, "Authentication failed", "Check node username/password")
                if r.status_code >= 500:
                    last_err = f"HTTP {r.status_code}"
                    continue
                page_type = detect_host_type(r.text, r.headers.get("content-type", ""))
                if page_type in ("openwrt", "openwrt_strata"):
                    detail = OPENWRT_STRATA_HINT if page_type == "openwrt_strata" else ROUTER_HINT
                    return NodeHealth(
                        False,
                        "OpenWrt admin UI — no BlueUp Transport menu here",
                        detail,
                        device_type=page_type,
                    )
                if r.status_code == 200 and page_type == "blueapro":
                    return NodeHealth(
                        True,
                        "BlueApro web UI detected",
                        PUSH_MODE_HINT,
                        device_type="blueapro",
                    )
                if path != "/" and r.status_code == 200:
                    try:
                        if r.headers.get("content-type", "").startswith("application/json"):
                            return NodeHealth(
                                True,
                                f"Node reachable ({path})",
                                PUSH_MODE_HINT,
                                device_type="blueapro",
                            )
                    except Exception:
                        pass
            except requests.RequestException as e:
                last_err = str(e)

        if page_type == "generic_web":
            return NodeHealth(
                False,
                "HTTP device is not a BlueApro BLE gateway",
                (last_err + "\n\n" if last_err else "") + PUSH_MODE_HINT,
                device_type="generic",
            )

        return NodeHealth(False, "Cannot reach BlueApro node", last_err or dev_err)

    def probe_endpoints(self) -> list[tuple[str, int, str]]:
        """Diagnostic: try all known paths and return status summaries."""
        results: list[tuple[str, int, str]] = []
        seen: set[str] = set()
        for path in [self.devices_path, *self.FALLBACK_DEVICE_PATHS, *self.FALLBACK_HEALTH_PATHS]:
            if path in seen:
                continue
            seen.add(path)
            try:
                r = self._session.get(self._url(path), timeout=self.timeout)
                hint = detect_host_type(r.text, r.headers.get("content-type", ""))
                results.append((path, r.status_code, hint))
            except requests.RequestException as e:
                results.append((path, -1, str(e)[:80]))
        return results

    def fetch_devices(self) -> tuple[list[NodeDevice], str]:
        paths = [self.devices_path] + [p for p in self.FALLBACK_DEVICE_PATHS if p != self.devices_path]
        last_err = ""
        tried: list[str] = []
        for path in paths:
            tried.append(path)
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
                if detect_host_type(r.text, r.headers.get("content-type", "")) == "openwrt":
                    return [], "Host is OpenWrt router — not a tag scanner. " + ROUTER_HINT.replace("\n", " ")
                devices = parse_device_payload(r.text, r.headers.get("content-type", ""))
                if devices:
                    return devices, ""
                last_err = f"{path} returned no devices"
            except requests.RequestException as e:
                last_err = str(e)
        summary = f"No BLE API ({', '.join(tried[:3])}… all missing). Use Push mode."
        return [], summary if "not found" in (last_err or "") else (last_err or summary)

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
