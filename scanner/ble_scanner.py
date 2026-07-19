"""
HOLO-RTLS Scanner Node — BLE Scanner
Uses bleak (cross-platform BLE) to scan for BLE advertising devices.

Requirements:
  pip install bleak

Works on: Linux (BlueZ), macOS, Windows, Raspberry Pi (BlueZ).
"""
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BLEDevice:
    mac_address: str
    rssi: int
    adv_name: str | None
    signal_type: int = 2   # 2 = BLE


class BLEScanner:
    """
    Scans for BLE advertising devices using bleak.
    Works cross-platform (Linux, macOS, Windows, Raspberry Pi).

    Usage:
        scanner = BLEScanner(adapter="hci0", rssi_min=-90)
        scanner.start()
        time.sleep(10)
        devices = scanner.get_recent_devices()
        scanner.stop()
    """

    def __init__(self, adapter: str | None = None,
                 rssi_min: int = -90,
                 scan_duration: float = 1.0):
        self.adapter   = adapter
        self.rssi_min = rssi_min
        self.scan_duration = scan_duration
        self._running  = False
        self._thread   = None
        # MAC → {rssi, adv_name, last_seen}
        self._devices: dict = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._thread.start()
        logger.info(f"BLE scanner started (adapter={self.adapter or 'default'})")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("BLE scanner stopped")

    def get_recent_devices(self, max_age_sec: float = 5.0) -> list[BLEDevice]:
        now = time.time()
        results = []
        for mac, data in list(self._devices.items()):
            if now - data["last_seen"] > max_age_sec:
                del self._devices[mac]
                continue
            results.append(BLEDevice(
                mac_address=mac,
                rssi=data["rssi"],
                adv_name=data["adv_name"],
                signal_type=2,
            ))
        return results

    def clear(self):
        self._devices.clear()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _scan_loop(self):
        try:
            import asyncio
        except ImportError:
            logger.error("asyncio not available")
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_scan())
        except Exception as e:
            logger.error(f"BLE scan error: {e}")
        finally:
            loop.close()

    async def _async_scan(self):
        try:
            from bleak import BleakScanner
        except ImportError:
            logger.error("bleak not installed. Run: pip install bleak")
            self._running = False
            return

        scanner = BleakScanner(adapter=self.adapter)

        while self._running:
            try:
                results = await scanner.get_discovered_devices()
                now = time.time()
                for dev in results:
                    # BLEAK returns rssi as metadata
                    rssi = dev.rssi if dev.rssi is not None else -80
                    if rssi < self.rssi_min:
                        continue
                    self._devices[dev.address.upper()] = {
                        "rssi": rssi,
                        "adv_name": dev.name,
                        "last_seen": now,
                    }
            except Exception as e:
                logger.warning(f"BLE scan iteration error: {e}")

            await asyncio.sleep(self.scan_duration)


# ── Mock BLE scanner (for testing without BLE hardware) ───────────────────────
class MockBLEScanner:
    """
    Returns fake BLE advertising data for development/testing.
    """
    def __init__(self, rssi_min: int = -90):
        self.rssi_min = rssi_min
        self._running = False
        self._thread  = None
        self._devices = {}
        self._macs = [
            "AA:00:00:00:00:01", "AA:00:00:00:00:02",
            "AA:00:00:00:00:03", "AA:00:00:00:00:04",
            "AA:00:00:00:00:05",
        ]

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._mock_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def get_recent_devices(self, max_age_sec: float = 5.0) -> list[BLEDevice]:
        now = time.time()
        results = []
        for mac, data in list(self._devices.items()):
            if now - data["last_seen"] > max_age_sec:
                del self._devices[mac]
                continue
            results.append(BLEDevice(
                mac_address=mac,
                rssi=data["rssi"],
                adv_name=data["adv_name"],
                signal_type=2,
            ))
        return results

    def clear(self):
        self._devices.clear()

    def _mock_loop(self):
        import random, math
        t = 0.0
        while self._running:
            for i, mac in enumerate(self._macs):
                phase = 2 * math.pi * i / len(self._macs)
                rssi = int(-60 + 8 * math.sin(t + phase))
                self._devices[mac] = {
                    "rssi": rssi,
                    "adv_name": f"BLE-TAG-{i+1}",
                    "last_seen": time.time(),
                }
            time.sleep(0.5)
            t += 0.5
