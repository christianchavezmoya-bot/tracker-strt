"""BLE tag classification (MOKO H7, iBeacon, Eddystone)."""
from __future__ import annotations

TAG_KEYWORDS = ("moko", "mkbn", "mkbnh7", "h7", "strata", "mk_", "mkb", "bxp")
APPLE_CID = 0x004C

SCAN_TYPE_LABELS = {
    "MOKO_H7": "MOKO H7 / MKBNH7",
    "IBEACON": "iBeacon",
    "EDDYSTONE": "Eddystone",
    "UNKNOWN_BLE": "Unknown BLE",
}


def parse_ibeacon(mfg: dict) -> str | None:
    data = mfg.get(APPLE_CID)
    if data and len(data) >= 23 and data[0] == 0x02 and data[1] == 0x15:
        uuid = data[2:18].hex()
        major = int.from_bytes(data[18:20], "big")
        minor = int.from_bytes(data[20:22], "big")
        tx = int.from_bytes(data[22:23], "big", signed=True)
        return f"iBeacon uuid={uuid} major={major} minor={minor} tx={tx}dBm"
    return None


def parse_eddystone(svc_data: dict) -> str | None:
    for k, v in svc_data.items():
        if k.lower().startswith("0000feaa") and v:
            frame = {0x00: "UID", 0x10: "URL", 0x20: "TLM", 0x30: "EID"}.get(v[0], hex(v[0]))
            return f"Eddystone-{frame} data={v.hex()}"
    return None


def classify_scan_type(name: str, ibeacon: str | None, eddystone: str | None, uuids: list) -> str:
    n = (name or "").lower()
    if any(k in n for k in ("moko", "mkbn", "mkbnh7", "bxp")):
        return "MOKO_H7"
    if ibeacon:
        return "IBEACON"
    if eddystone or any(u.lower().startswith("0000feaa") for u in uuids):
        return "EDDYSTONE"
    if any(k in n for k in TAG_KEYWORDS):
        return "MOKO_H7"
    return "UNKNOWN_BLE"


def is_tag_candidate(name: str, ibeacon: str | None, eddystone: str | None, uuids: list) -> bool:
    n = (name or "").lower()
    if any(k in n for k in TAG_KEYWORDS):
        return True
    if ibeacon or eddystone:
        return True
    if any(u.lower().startswith("0000feaa") for u in uuids):
        return True
    return False
