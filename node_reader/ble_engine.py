"""Async BLE scanning engine (bleak) for the node reader."""
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field

from node_reader.tag_classifier import (
    classify_scan_type,
    is_tag_candidate,
    parse_eddystone,
    parse_ibeacon,
)


@dataclass
class TagDetection:
    mac: str
    name: str = ""
    rssi: int = -999
    scan_type: str = "UNKNOWN_BLE"
    ibeacon: str | None = None
    eddystone: str | None = None
    is_candidate: bool = False
    last_seen: float = field(default_factory=time.time)
    raw_mfg: dict = field(default_factory=dict)
    raw_svc: dict = field(default_factory=dict)
    uuids: list = field(default_factory=list)

    @property
    def strength(self) -> str:
        if self.rssi >= -70:
            return "STRONG"
        if self.rssi >= -90:
            return "MEDIUM"
        return "WEAK"


class BLEScanEngine:
    """Background BLE scanner using bleak."""

    def __init__(self, rssi_min: int = -90, tags_only: bool = False):
        self.rssi_min = rssi_min
        self.tags_only = tags_only
        self._devices: dict[str, TagDetection] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._scanner = None
        self.on_update = None  # callback(TagDetection, is_new)

    def get_all(self) -> list[TagDetection]:
        with self._lock:
            return sorted(self._devices.values(), key=lambda d: -d.rssi)

    def clear(self) -> None:
        with self._lock:
            self._devices.clear()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="BLEScan")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._async_stop(), self._loop)
        if self._thread:
            self._thread.join(timeout=8)

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_run())
        except Exception:
            pass
        finally:
            self._loop.close()

    async def _async_run(self) -> None:
        from bleak import BleakScanner

        def callback(device, adv):
            if not self._running:
                return
            addr = device.address.upper()
            name = adv.local_name or device.name or ""
            rssi = adv.rssi if adv.rssi is not None else -999
            if rssi < self.rssi_min:
                return
            mfg = dict(adv.manufacturer_data)
            svc = dict(adv.service_data)
            uuids = list(adv.service_uuids)
            ib = parse_ibeacon(mfg)
            ed = parse_eddystone(svc)
            cand = is_tag_candidate(name, ib, ed, uuids)
            if self.tags_only and not cand:
                return
            st = classify_scan_type(name, ib, ed, uuids)
            with self._lock:
                is_new = addr not in self._devices
                rec = self._devices.get(addr)
                if rec is None:
                    rec = TagDetection(mac=addr)
                    self._devices[addr] = rec
                if name and name.lower() != "unknown":
                    rec.name = name
                rec.rssi = max(rec.rssi, rssi)
                rec.scan_type = st
                rec.ibeacon = ib
                rec.eddystone = ed
                rec.is_candidate = cand
                rec.last_seen = time.time()
                rec.raw_mfg = mfg
                rec.raw_svc = svc
                rec.uuids = uuids
            if self.on_update:
                try:
                    self.on_update(rec, is_new)
                except Exception:
                    pass

        self._scanner = BleakScanner(detection_callback=callback)
        await self._scanner.start()
        while self._running:
            await asyncio.sleep(0.2)
        await self._async_stop()

    async def _async_stop(self) -> None:
        if self._scanner:
            try:
                await self._scanner.stop()
            except Exception:
                pass
            self._scanner = None
