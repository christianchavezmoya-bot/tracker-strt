"""
HOLO-RTLS — Tracker discovery: classify BLE/WiFi devices and upsert unacknowledged tags.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.extensions import db
from backend.models import Tracker, WifiNode, TrackerAckStatus, AssetState, TagType, DeviceCategory
from backend.models.detection import DetectionEvent, SignalType
from backend.models.settings import Setting
from backend.models.positioning import TrackerPresenceLog

logger = logging.getLogger(__name__)

APPLE_CID = 0x004C
MSFT_CID = 0x0006
SAMSUNG_CID = 0x0075
GARMIN_CID = 0x0087

# Scan types selectable in UI (from BLE scan report + MOKO)
SCAN_TYPES = {
    "MOKO_H7": {
        "label": "MOKO H7 / MKBNH7",
        "model": "MOKO H7",
        "keywords": ("moko", "mkbn", "mkbnh7", "mkbnh7"),
    },
    "IBEACON": {
        "label": "iBeacon",
        "model": "iBeacon Tag",
    },
    "EDDYSTONE": {
        "label": "Eddystone (UID/TLM)",
        "model": "Eddystone Beacon",
    },
    "APPLE_NEARBY": {
        "label": "Apple Nearby / Continuity",
        "model": "Apple Device",
        "mfg_id": APPLE_CID,
    },
    "MICROSOFT_SWIFT_PAIR": {
        "label": "Microsoft Swift Pair",
        "model": "Windows PC",
        "mfg_id": MSFT_CID,
    },
    "GOOGLE_FAST_PAIR": {
        "label": "Google Fast Pair",
        "model": "Fast Pair Device",
        "service_uuid": "0000fcf1-0000-1000-8000-00805f9b34fb",
    },
    "SAMSUNG": {
        "label": "Samsung BLE",
        "model": "Samsung Device",
        "mfg_id": SAMSUNG_CID,
    },
    "GARMIN": {
        "label": "Garmin Wearable",
        "model": "Garmin Device",
        "mfg_id": GARMIN_CID,
    },
    "UNKNOWN_BLE": {
        "label": "Unknown BLE",
        "model": "Unknown BLE",
    },
}

# Confirmed implementable features per scan type (do not list direction / true depth)
FEATURES_BY_SCAN_TYPE: dict[str, list[dict]] = {
    "MOKO_H7": [
        {"key": "positioning", "label": "Indoor positioning (RSSI)"},
        {"key": "proximity", "label": "Proximity alerts"},
        {"key": "restricted_zone", "label": "No-go / restricted zones"},
        {"key": "low_battery", "label": "Low battery alert"},
        {"key": "no_signal", "label": "No signal / offline alert"},
        {"key": "lone_worker", "label": "Lone worker / no movement"},
        {"key": "sos", "label": "SOS button alert"},
        {"key": "temperature", "label": "Temperature (Eddystone TLM)"},
    ],
    "IBEACON": [
        {"key": "positioning", "label": "Indoor positioning (RSSI)"},
        {"key": "proximity", "label": "Proximity alerts"},
        {"key": "restricted_zone", "label": "No-go / restricted zones"},
        {"key": "no_signal", "label": "No signal / offline alert"},
    ],
    "EDDYSTONE": [
        {"key": "positioning", "label": "Indoor positioning (RSSI)"},
        {"key": "proximity", "label": "Proximity alerts"},
        {"key": "restricted_zone", "label": "No-go / restricted zones"},
        {"key": "low_battery", "label": "Low battery (TLM voltage)"},
        {"key": "temperature", "label": "Temperature (TLM)"},
        {"key": "no_signal", "label": "No signal / offline alert"},
    ],
    "APPLE_NEARBY": [
        {"key": "positioning", "label": "Approximate positioning (WiFi/BLE RSSI)"},
        {"key": "no_signal", "label": "No signal / offline alert"},
    ],
    "MICROSOFT_SWIFT_PAIR": [
        {"key": "positioning", "label": "Approximate positioning (WiFi probe RSSI)"},
        {"key": "no_signal", "label": "No signal / offline alert"},
    ],
    "GOOGLE_FAST_PAIR": [
        {"key": "positioning", "label": "Approximate positioning (BLE RSSI)"},
        {"key": "no_signal", "label": "No signal / offline alert"},
    ],
    "SAMSUNG": [
        {"key": "positioning", "label": "Approximate positioning (BLE RSSI)"},
        {"key": "proximity", "label": "Proximity alerts"},
        {"key": "no_signal", "label": "No signal / offline alert"},
    ],
    "GARMIN": [
        {"key": "positioning", "label": "Approximate positioning (BLE RSSI)"},
        {"key": "no_signal", "label": "No signal / offline alert"},
    ],
    "UNKNOWN_BLE": [
        {"key": "positioning", "label": "Indoor positioning (RSSI)"},
        {"key": "no_signal", "label": "No signal / offline alert"},
    ],
}

DEFAULT_SCAN_TYPES = ["MOKO_H7", "IBEACON", "EDDYSTONE"]
DEFAULT_SCAN_INTERVAL_SEC = 60
PRESENCE_RETENTION_HOURS = 25


def _log_presence(tracker_id: int, online: bool, rssi: float | None = None) -> None:
    db.session.add(TrackerPresenceLog(
        tracker_id=tracker_id,
        online=online,
        rssi=rssi,
    ))


def _prune_presence_logs() -> None:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=PRESENCE_RETENTION_HOURS)
    TrackerPresenceLog.query.filter(TrackerPresenceLog.timestamp < cutoff).delete(synchronize_session=False)


@dataclass
class DiscoveredDevice:
    hardware_id: str
    scan_type: str
    device_model: str
    adv_name: str = ""
    rssi: float = -999.0
    battery_level: Optional[float] = None
    temperature: Optional[float] = None
    beacons: list = field(default_factory=list)


def _setting_json(key: str, default):
    row = Setting.query.filter_by(key=key).first()
    if not row or not row.value:
        return default
    try:
        return json.loads(row.value)
    except Exception:
        return default


def get_scan_config() -> dict:
    types = _setting_json("tracker_scan_types", DEFAULT_SCAN_TYPES)
    interval = _setting_json("tracker_scan_interval_sec", DEFAULT_SCAN_INTERVAL_SEC)
    if interval not in (30, 60, 120):
        interval = DEFAULT_SCAN_INTERVAL_SEC
    return {
        "scan_types": types,
        "interval_sec": interval,
        "scan_types_catalog": [
            {"id": k, "label": v["label"], "model": v.get("model", k)}
            for k, v in SCAN_TYPES.items()
        ],
    }


def save_scan_config(scan_types: list, interval_sec: int) -> dict:
    if interval_sec not in (30, 60, 120):
        interval_sec = DEFAULT_SCAN_INTERVAL_SEC
    valid = [t for t in scan_types if t in SCAN_TYPES]
    if not valid:
        valid = DEFAULT_SCAN_TYPES[:]

    for key, val in [
        ("tracker_scan_types", json.dumps(valid)),
        ("tracker_scan_interval_sec", json.dumps(interval_sec)),
    ]:
        row = Setting.query.filter_by(key=key).first()
        if row:
            row.value = val
        else:
            db.session.add(Setting(key=key, value=val))
    db.session.commit()
    return get_scan_config()


def classify_detection(mac: str, adv_name: str = "", mfg_hint: str = "",
                     has_ibeacon: bool = False, has_eddystone: bool = False,
                     service_uuids: list | None = None) -> str:
    name = (adv_name or "").lower()
    if any(k in name for k in SCAN_TYPES["MOKO_H7"]["keywords"]):
        return "MOKO_H7"
    if has_ibeacon:
        return "IBEACON"
    if has_eddystone:
        return "EDDYSTONE"
    uuids = [u.lower() for u in (service_uuids or [])]
    if any("fcf1" in u for u in uuids):
        return "GOOGLE_FAST_PAIR"
    if any("feaa" in u for u in uuids):
        return "EDDYSTONE"
    mfg = mfg_hint.upper()
    if "004C" in mfg or "APPLE" in mfg:
        return "APPLE_NEARBY"
    if "0006" in mfg or "MICROSOFT" in mfg:
        return "MICROSOFT_SWIFT_PAIR"
    if "0075" in mfg or "SAMSUNG" in mfg:
        return "SAMSUNG"
    if "0087" in mfg or "GARMIN" in mfg:
        return "GARMIN"
    return "UNKNOWN_BLE"


def _aggregate_from_detection_events(since: datetime) -> dict[str, DiscoveredDevice]:
    """Build discovery map from scanner anchor detection_events."""
    from backend.models.detection import WifiAnchor

    events = (
        DetectionEvent.query
        .filter(DetectionEvent.timestamp >= since)
        .order_by(DetectionEvent.timestamp.desc())
        .limit(5000)
        .all()
    )
    anchor_names = {
        a.id: a.name or a.mac_address
        for a in WifiAnchor.query.all()
    }
    # Also map wifi_nodes used by scanner path
    for n in WifiNode.query.all():
        pass

    by_mac: dict[str, DiscoveredDevice] = {}
    beacon_map: dict[str, dict[str, float]] = {}

    for ev in events:
        mac = (ev.mac_address or "").upper()
        if not mac:
            continue
        st = "UNKNOWN_BLE"
        if ev.signal_type == int(SignalType.WIFI):
            st = "MICROSOFT_SWIFT_PAIR"  # probes often from laptops/phones
        adv = ev.adv_name or ""
        if ev.signal_type == int(SignalType.BLE):
            st = classify_detection(mac, adv_name=adv)

        anchor_label = anchor_names.get(ev.anchor_id, f"Anchor-{ev.anchor_id}")
        beacon_map.setdefault(mac, {})[anchor_label] = max(
            beacon_map[mac].get(anchor_label, -999), float(ev.rssi)
        )

        if mac not in by_mac:
            meta = SCAN_TYPES.get(st, SCAN_TYPES["UNKNOWN_BLE"])
            by_mac[mac] = DiscoveredDevice(
                hardware_id=mac,
                scan_type=st,
                device_model=meta.get("model", st),
                adv_name=adv,
                rssi=float(ev.rssi),
            )
        else:
            by_mac[mac].rssi = max(by_mac[mac].rssi, float(ev.rssi))
            if adv and not by_mac[mac].adv_name:
                by_mac[mac].adv_name = adv

    for mac, dev in by_mac.items():
        beacons = beacon_map.get(mac, {})
        dev.beacons = [
            {"node": node, "rssi": rssi}
            for node, rssi in sorted(beacons.items(), key=lambda x: -x[1])
        ]
    return by_mac


def _try_bleak_scan(duration: int = 8) -> dict[str, DiscoveredDevice]:
    """Optional local BLE scan when bleak + adapter available."""
    try:
        import asyncio
        from bleak import BleakScanner
    except ImportError:
        return {}

    APPLE = 0x004C
    found: dict[str, DiscoveredDevice] = {}

    def _cb(device, adv):
        mac = device.address.upper()
        name = adv.local_name or device.name or ""
        rssi = adv.rssi if adv.rssi is not None else -999
        mfg = dict(adv.manufacturer_data)
        svc = dict(adv.service_data)
        uuids = list(adv.service_uuids)
        has_ib = bool(mfg.get(APPLE) and len(mfg[APPLE]) >= 23 and mfg[APPLE][0] == 0x02)
        has_ed = any(k.lower().startswith("0000feaa") for k in svc)
        mfg_hint = ",".join(f"{k:04X}" for k in mfg.keys())
        st = classify_detection(mac, name, mfg_hint, has_ib, has_ed, uuids)
        meta = SCAN_TYPES.get(st, SCAN_TYPES["UNKNOWN_BLE"])
        bat = temp = None
        for k, v in svc.items():
            if k.lower().startswith("0000feaa") and v and v[0] == 0x20 and len(v) >= 6:
                bat_mv = int.from_bytes(v[2:4], "big")
                bat = round(bat_mv / 30.0, 1) if bat_mv else None  # rough CR2032 %
                temp_raw = int.from_bytes(v[4:6], "big", signed=True)
                temp = temp_raw if abs(temp_raw) < 128 else None
        if mac not in found or rssi > found[mac].rssi:
            found[mac] = DiscoveredDevice(
                hardware_id=mac, scan_type=st, device_model=meta.get("model", st),
                adv_name=name, rssi=rssi, battery_level=bat, temperature=temp,
                beacons=[{"node": "Local BLE", "rssi": rssi}],
            )

    async def _run():
        scanner = BleakScanner(detection_callback=_cb)
        await scanner.start()
        await asyncio.sleep(duration)
        await scanner.stop()

    try:
        asyncio.run(_run())
    except Exception as e:
        logger.debug("Bleak scan skipped: %s", e)
        return {}
    return found


def run_discovery() -> dict:
    """Discover tags matching configured scan types; upsert unacknowledged trackers."""
    cfg = get_scan_config()
    allowed = set(cfg["scan_types"])
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)

    merged: dict[str, DiscoveredDevice] = _aggregate_from_detection_events(since)
    bleak_found = _try_bleak_scan(duration=min(12, cfg["interval_sec"] // 5 or 8))
    for mac, dev in bleak_found.items():
        if mac not in merged or dev.rssi > merged[mac].rssi:
            merged[mac] = dev
        elif mac in merged and not merged[mac].beacons:
            merged[mac].beacons = dev.beacons

    created = updated = skipped = 0
    no_signal_timeout = 120
    try:
        row = Setting.query.filter_by(key="no_signal_timeout").first()
        if row and row.value:
            no_signal_timeout = int(float(row.value))
    except Exception:
        pass
    now_ts = time.time()
    cutoff = now_ts - no_signal_timeout

    for mac, dev in merged.items():
        if dev.scan_type not in allowed:
            skipped += 1
            continue

        tracker = Tracker.query.filter_by(hardware_id=mac).first()
        nearest = dev.beacons[0]["node"] if dev.beacons else None
        beacon_str = json.dumps(dev.beacons)
        default_feats = {f["key"]: True for f in FEATURES_BY_SCAN_TYPE.get(dev.scan_type, [])}

        if tracker:
            tracker.last_rssi = dev.rssi
            tracker.nearest_node = nearest
            tracker.beacon_json = beacon_str
            tracker.last_report_time = now_ts
            if dev.battery_level is not None:
                tracker.battery_level = dev.battery_level
            if dev.temperature is not None:
                tracker.temperature = dev.temperature
            if not tracker.device_model:
                tracker.device_model = dev.device_model
            if not tracker.scan_type:
                tracker.scan_type = dev.scan_type
            if tracker.ack_status == int(TrackerAckStatus.ACTIVE):
                tracker.asset_state = int(AssetState.ACTIVE)
            elif tracker.ack_status == int(TrackerAckStatus.UNACKNOWLEDGED):
                pass
            _log_presence(tracker.id, True, dev.rssi)
            updated += 1
        else:
            tracker = Tracker(
                hardware_id=mac,
                assigned_name=dev.adv_name or None,
                device_model=dev.device_model,
                scan_type=dev.scan_type,
                ack_status=int(TrackerAckStatus.UNACKNOWLEDGED),
                asset_state=int(AssetState.OFFLINE),
                last_rssi=dev.rssi,
                nearest_node=nearest,
                beacon_json=beacon_str,
                features_json=json.dumps(default_feats),
                last_report_time=now_ts,
                battery_level=dev.battery_level if dev.battery_level is not None else 100.0,
                temperature=dev.temperature,
            )
            db.session.add(tracker)
            db.session.flush()
            _log_presence(tracker.id, True, dev.rssi)
            created += 1

    seen_ids = set()
    for mac, dev in merged.items():
        if dev.scan_type not in allowed:
            continue
        t = Tracker.query.filter_by(hardware_id=mac).first()
        if t:
            seen_ids.add(t.id)

    # Mark acknowledged active tags offline if not seen this scan
    for t in Tracker.query.filter(
        Tracker.ack_status == int(TrackerAckStatus.ACTIVE)
    ).all():
        if t.id in seen_ids:
            t.asset_state = int(AssetState.ACTIVE)
        elif t.last_report_time and t.last_report_time < cutoff:
            t.asset_state = int(AssetState.OFFLINE)
            _log_presence(t.id, False, t.last_rssi)
        elif t.id not in seen_ids:
            t.asset_state = int(AssetState.OFFLINE)
            _log_presence(t.id, False, t.last_rssi)

    _prune_presence_logs()
    db.session.commit()
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "discovered": len(merged),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def purge_trackers(tracker_ids: list[int]) -> int:
    """Reset tags to unacknowledged — clears profile fields."""
    count = 0
    for tid in tracker_ids:
        t = Tracker.query.get(tid)
        if not t:
            continue
        t.ack_status = int(TrackerAckStatus.UNACKNOWLEDGED)
        t.asset_state = int(AssetState.OFFLINE)
        t.nickname = t.first_name = t.surname = t.username = None
        t.position_id = t.org_section_id = None
        t.date_of_birth = t.phone = None
        t.assigned_name = None
        t.features_json = json.dumps({
            f["key"]: True for f in FEATURES_BY_SCAN_TYPE.get(t.scan_type or "UNKNOWN_BLE", [])
        })
        count += 1
    db.session.commit()
    return count


def acknowledge_tracker(tracker_id: int, body: dict) -> Optional[Tracker]:
    t = Tracker.query.get(tracker_id)
    if not t:
        return None
    for field in ["nickname", "first_name", "surname", "username",
                  "date_of_birth", "phone", "position_id", "org_section_id"]:
        if field in body:
            setattr(t, field, body[field] or None)
    if "assigned_name" in body:
        t.assigned_name = body["assigned_name"]
    elif body.get("nickname"):
        t.assigned_name = body["nickname"]
    if "features" in body and isinstance(body["features"], dict):
        t.features_json = json.dumps(body["features"])
    if "tag_type" in body:
        t.tag_type = int(body["tag_type"])
    if "category" in body:
        t.category = int(body["category"])
    t.ack_status = int(TrackerAckStatus.ACTIVE)
    t.asset_state = int(AssetState.ACTIVE) if t.last_report_time else int(AssetState.OFFLINE)
    db.session.commit()
    return t
