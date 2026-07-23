"""Server time, timezone, and NTP guidance for node configuration."""
from __future__ import annotations

from datetime import datetime, timezone
import platform
import subprocess
from zoneinfo import ZoneInfo

from backend.extensions import db
from backend.models.settings import Setting
from backend.services.settings_defaults import SETTING_DEFAULTS
from backend.services.mqtt_broker_manager import get_broker_advertised_host

TIMEZONE_KEY = "display_timezone"
NODE_TIMEZONE_KEY = "node_timezone"
NODE_NTP_SERVER_KEY = "node_ntp_server"
NODE_NTP_MODE_KEY = "node_ntp_mode"
CLOCK_SKEW_WARN_KEY = "node_clock_skew_warn_seconds"


def _setting_value(key: str, default=None):
    row = db.session.query(Setting).filter_by(key=key).first()
    if row is not None:
        try:
            value = row.get_typed_value()
        except Exception:
            value = row.value
        if value not in (None, ""):
            return value
    meta = SETTING_DEFAULTS.get(key)
    if meta:
        raw = meta.get("value")
        value_type = meta.get("value_type")
        if value_type == "int":
            try:
                return int(raw)
            except Exception:
                return default
        if value_type == "float":
            try:
                return float(raw)
            except Exception:
                return default
        if value_type == "bool":
            return str(raw).lower() in ("1", "true", "yes", "on")
        return raw
    return default


def _safe_zone(zone_name: str | None) -> str:
    value = (zone_name or "UTC").strip() or "UTC"
    try:
        ZoneInfo(value)
        return value
    except Exception:
        return "UTC"


def _effective_node_ntp_server() -> str:
    configured = str(_setting_value(NODE_NTP_SERVER_KEY, "") or "").strip()
    if configured:
        return configured
    return get_broker_advertised_host()


def _windows_ntp_status() -> dict:
    service_state = "unknown"
    source = None
    stratum = None
    last_sync = None
    detail = None
    try:
        svc = subprocess.run(
            ["sc", "query", "W32Time"],
            capture_output=True, text=True, timeout=3,
        )
        output = (svc.stdout or "") + "\n" + (svc.stderr or "")
        if "RUNNING" in output:
            service_state = "running"
        elif "STOPPED" in output:
            service_state = "stopped"
    except Exception as exc:
        detail = str(exc)

    try:
        res = subprocess.run(
            ["w32tm", "/query", "/status"],
            capture_output=True, text=True, timeout=3,
        )
        output = (res.stdout or "")
        for line in output.splitlines():
            if ":" not in line:
                continue
            left, right = line.split(":", 1)
            key = left.strip().lower()
            value = right.strip()
            if key == "source":
                source = value
            elif key == "stratum":
                stratum = value
            elif key == "last successful sync time":
                last_sync = value
        if detail is None and res.returncode != 0:
            detail = (res.stderr or res.stdout or "").strip() or "w32tm returned non-zero status"
    except Exception as exc:
        if detail is None:
            detail = str(exc)

    status = "ok"
    if service_state != "running":
        status = "warning"
    if source and source.lower() == "local cmos clock":
        status = "warning"
    if not source and detail:
        status = "unknown"

    return {
        "platform": "windows",
        "service_state": service_state,
        "source": source,
        "stratum": stratum,
        "last_sync": last_sync,
        "status": status,
        "detail": detail,
    }


def _generic_ntp_status() -> dict:
    return {
        "platform": platform.system().lower(),
        "service_state": "unknown",
        "source": None,
        "stratum": None,
        "last_sync": None,
        "status": "unknown",
        "detail": "Host NTP service inspection is not implemented for this platform.",
    }


def ntp_status_summary() -> dict:
    if platform.system().lower().startswith("win"):
        return _windows_ntp_status()
    return _generic_ntp_status()


def time_sync_status_summary() -> dict:
    display_tz = _safe_zone(str(_setting_value(TIMEZONE_KEY, "UTC") or "UTC"))
    node_tz = _safe_zone(str(_setting_value(NODE_TIMEZONE_KEY, display_tz) or display_tz))
    node_ntp_mode = str(_setting_value(NODE_NTP_MODE_KEY, "lan_server") or "lan_server")
    node_ntp_server = _effective_node_ntp_server()
    clock_skew_warn = int(_setting_value(CLOCK_SKEW_WARN_KEY, 10) or 10)

    now_utc = datetime.now(timezone.utc)
    local_now = now_utc.astimezone(ZoneInfo(display_tz))
    ntp = ntp_status_summary()

    return {
        "server_time_utc": now_utc.isoformat(),
        "server_time_local": local_now.isoformat(),
        "display_timezone": display_tz,
        "node_timezone": node_tz,
        "node_ntp_mode": node_ntp_mode,
        "node_ntp_server": node_ntp_server,
        "clock_skew_warn_seconds": clock_skew_warn,
        "broker_host_hint": get_broker_advertised_host(),
        "ntp": ntp,
        "guidance": {
            "internal_time_rule": "Store and compare all RTLS events in UTC.",
            "node_rule": "Use server receive time as the authoritative event time for tracking.",
            "operator_rule": "Node-reported time is for diagnostics and clock-drift checks only.",
            "windows_ntp_note": "If nodes should use this PC as NTP, Windows must be configured to serve time on the LAN. The Flask app does not provide NTP.",
            "windows_ntp_steps": [
                "Ensure the Windows Time service (W32Time) is running.",
                "Configure the host or another LAN device to act as the NTP source.",
                "Allow UDP 123 on the LAN interface.",
                "Set each node's NTP server to the chosen LAN IP and timezone to UTC.",
            ],
        },
    }
