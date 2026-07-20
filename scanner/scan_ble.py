#!/usr/bin/env python3
"""HOLO-RTLS — standalone BLE tag scanner (Windows / macOS / Linux, via bleak).

Scans for nearby Bluetooth Low Energy devices, decodes iBeacon / Eddystone
frames, and flags likely asset tags (MOKO H7 / MKBNH7, Strata, etc.) so you can
identify which advertisers are yours.

Usage:
    python scanner/scan_ble.py                  # 20s scan, show everything
    python scanner/scan_ble.py -d 30            # 30-second scan
    python scanner/scan_ble.py -f strata        # only names/MACs containing "strata"
    python scanner/scan_ble.py --min-rssi -70   # only STRONG (nearby) devices
    python scanner/scan_ble.py --tags-only      # only show flagged tag candidates

Requires: pip install bleak   (and Bluetooth turned on)
"""
import argparse
import asyncio

from bleak import BleakScanner

# Names that mark a device as a likely asset tag we care about.
TAG_KEYWORDS = ("moko", "mkbn", "mkbnh7", "h7", "strata", "mk_", "mkb")
APPLE_CID = 0x004C  # 76 — iBeacon lives under Apple's company id


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


def is_candidate(name: str, ibeacon: str | None, eddystone: str | None, uuids: list) -> bool:
    n = (name or "").lower()
    if any(k in n for k in TAG_KEYWORDS):
        return True
    if ibeacon or eddystone:
        return True
    if any(u.lower().startswith("0000feaa") for u in uuids):
        return True
    return False


async def scan(duration: int, name_filter: str | None, min_rssi: int | None, tags_only: bool):
    hdr = f"  Scanning for {duration}s"
    if name_filter:
        hdr += f", filter='{name_filter}'"
    if min_rssi is not None:
        hdr += f", min RSSI {min_rssi} dBm"
    if tags_only:
        hdr += ", tag candidates only"
    print("=" * 70)
    print("  HOLO-RTLS - BLE Scanner  (watching for MOKO H7 / MKBNH7 tags)")
    print(hdr + " ... (bring a tag near the PC)")
    print("=" * 70)

    seen: dict[str, dict] = {}
    flt = (name_filter or "").lower()

    def callback(device, adv):
        addr = device.address
        name = adv.local_name or device.name or ""
        rssi = adv.rssi if adv.rssi is not None else -999
        mfg = dict(adv.manufacturer_data)
        svc = dict(adv.service_data)
        uuids = list(adv.service_uuids)

        if flt and flt not in name.lower() and flt not in addr.lower():
            return
        if min_rssi is not None and rssi < min_rssi:
            return

        rec = seen.get(addr, {"mac": addr, "name": "", "rssi": -999, "mfg": {}, "svc": {}, "uuids": []})
        # keep the best (real) name and strongest RSSI seen across the window
        if name and name.lower() != "unknown":
            rec["name"] = name
        rec["rssi"] = max(rec["rssi"], rssi)
        if mfg:
            rec["mfg"] = mfg
        if svc:
            rec["svc"] = svc
        if uuids:
            rec["uuids"] = uuids
        first = addr not in seen
        seen[addr] = rec

        ib = parse_ibeacon(mfg)
        ed = parse_eddystone(svc)
        cand = is_candidate(rec["name"], ib, ed, uuids)
        if cand:
            tag = "  <<< TAG CANDIDATE"
            beacon = f"  [{ib or ed}]" if (ib or ed) else ""
            print(f"[HIT] {addr}  {rssi:>4} dBm  {rec['name'] or 'Unknown'}{beacon}{tag}")
        elif first and not tags_only:
            print(f"[new] {addr}  {rssi:>4} dBm  {name or 'Unknown'}")

    scanner = BleakScanner(detection_callback=callback)
    await scanner.start()
    try:
        await asyncio.sleep(duration)
    finally:
        await scanner.stop()

    # ── Summary ──────────────────────────────────────────────────────────────
    results = sorted(seen.values(), key=lambda r: -r["rssi"])
    candidates = []
    for r in results:
        r["ibeacon"] = parse_ibeacon(r["mfg"])
        r["eddystone"] = parse_eddystone(r["svc"])
        if is_candidate(r["name"], r["ibeacon"], r["eddystone"], r["uuids"]):
            candidates.append(r)

    print("\n" + "=" * 70)
    print(f"  TAG CANDIDATES: {len(candidates)}  (of {len(results)} devices seen)")
    print("=" * 70)
    if not candidates:
        print("  none — power on a tag and hold it near the PC, then re-run.")
    for r in candidates:
        strength = "STRONG" if r["rssi"] >= -70 else ("MEDIUM" if r["rssi"] >= -90 else "weak")
        print(f"  [{strength}] {r['mac']}  {r['rssi']:>4} dBm  {r['name'] or 'Unknown'}")
        if r["ibeacon"]:
            print(f"           {r['ibeacon']}")
        if r["eddystone"]:
            print(f"           {r['eddystone']}")
        if r["mfg"]:
            print("           mfg=" + ", ".join(f"0x{k:04X}:{v.hex()}" for k, v in r["mfg"].items()))
        if r["uuids"]:
            print(f"           uuids={r['uuids']}")

    if not tags_only:
        print("\n  --- all devices (by signal) ---")
        for r in results:
            strength = "STRONG" if r["rssi"] >= -70 else ("MEDIUM" if r["rssi"] >= -90 else "weak")
            print(f"  [{strength}] {r['mac']}  {r['rssi']:>4} dBm  {r['name'] or 'Unknown'}")
    print("=" * 70)


def main():
    ap = argparse.ArgumentParser(description="HOLO-RTLS BLE tag scanner")
    ap.add_argument("-d", "--duration", type=int, default=20, help="scan seconds (default 20)")
    ap.add_argument("-f", "--filter", default=None, help="only show devices whose name or MAC contains this text")
    ap.add_argument("--min-rssi", type=int, default=None, help="only show devices at/above this RSSI, e.g. -70")
    ap.add_argument("--tags-only", action="store_true", help="only show flagged tag candidates")
    args = ap.parse_args()
    try:
        asyncio.run(scan(args.duration, args.filter, args.min_rssi, args.tags_only))
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        print("-> Is Bluetooth turned ON? (Windows: Settings > Bluetooth & devices)")
        print("-> A built-in or USB Bluetooth adapter is required. Install deps: pip install bleak")


if __name__ == "__main__":
    main()
