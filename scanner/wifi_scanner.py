"""
HOLO-RTLS Scanner Node — WiFi Scanner
Uses scapy to sniff probe requests in monitor mode.

Requirements:
  pip install scapy

On Linux, put your interface in monitor mode first:
  sudo ip link set wlan0 down
  sudo iw dev wlan0 set type monitor
  sudo ip link set wlan0 up
  # or use airmon-ng

NOTE: On macOS / Windows you cannot use scapy for WiFi sniffing without
special drivers. Use BLE scanning or a dedicated WiFi adapter in monitor mode.
"""
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class WifiProbe:
    mac_address: str
    rssi: int
    ssid: str | None
    channel: int | None
    signal_type: int = 1   # 1 = WiFi


class WifiScanner:
    """
    Scans for WiFi probe requests using scapy.
    Works on Linux with a monitor-mode interface.

    Usage:
        scanner = WifiScanner(interface="wlan0mon", rssi_min=-90)
        scanner.start()
        time.sleep(10)
        probes = scanner.get_recent_probes()
        scanner.stop()
    """

    def __init__(self, interface: str, rssi_min: int = -90,
                 scan_duration: float = 1.0):
        self.interface    = interface
        self.rssi_min     = rssi_min
        self.scan_duration = scan_duration
        self._running     = False
        self._thread      = None
        # MAC → {rssi, ssid, channel, last_seen}
        self._probes: dict = defaultdict(lambda: {"rssi": -100, "ssid": None, "channel": None, "last_seen": 0.0})

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._thread.start()
        logger.info(f"WiFi scanner started on {self.interface}")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("WiFi scanner stopped")

    def get_recent_probes(self, max_age_sec: float = 5.0) -> list[WifiProbe]:
        """Return probes seen within the last max_age_sec seconds."""
        now = time.time()
        results = []
        for mac, data in list(self._probes.items()):
            if now - data["last_seen"] > max_age_sec:
                del self._probes[mac]
                continue
            results.append(WifiProbe(
                mac_address=mac,
                rssi=data["rssi"],
                ssid=data["ssid"],
                channel=data["channel"],
                signal_type=1,
            ))
        return results

    def clear(self):
        self._probes.clear()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _scan_loop(self):
        try:
            from scapy.all import sniff, Dot11, Dot11ProbeReq, Dot11Elt
        except ImportError:
            logger.error("scapy not installed. Run: pip install scapy")
            self._running = False
            return

        def packet_handler(pkt):
            if not pkt.haslayer(Dot11ProbeReq):
                return
            if pkt.haslayer(Dot11):
                mac = pkt.addr2
                rssi = self._rssi_from_pkt(pkt)
                if rssi < self.rssi_min:
                    return

                ssid = None
                channel = None
                if pkt.haslayer(Dot11Elt):
                    elt = pkt[Dot11Elt]
                    while elt:
                        if elt.ID == 0:        # SSID
                            try:
                                ssid = elt.info.decode("utf-8", errors="ignore") or None
                            except Exception:
                                ssid = None
                        elif elt.ID == 3:      # DS parameter set (channel)
                            try:
                                channel = ord(elt.info) if elt.info else None
                            except Exception:
                                channel = None
                        elt = elt.payload.getlayer(Dot11Elt)

                if mac:
                    self._probes[mac] = {
                        "rssi": rssi,
                        "ssid": ssid,
                        "channel": channel,
                        "last_seen": time.time(),
                    }

        sniff(iface=self.interface, prn=packet_handler,
              store=False, monitor=True)

    @staticmethod
    def _rssi_from_pkt(pkt) -> int:
        """Extract RSSI from scapy packet (varies by OS/driver)."""
        # Not all drivers expose this. Scapy doesn't standardise it.
        # For real hardware, check radiotap headers.
        try:
            if hasattr(pkt, "dBm_AntSignal"):
                return int(pkt.dBm_AntSignal)
        except Exception:
            pass
        return -70   # fallback — calibrate against your hardware


# ── Mock scanner (for testing without monitor mode) ───────────────────────────
class MockWifiScanner:
    """
    Returns fake probe data for development/testing.
    Simulates 5 devices wandering around.
    """
    def __init__(self, rssi_min: int = -90):
        self.rssi_min = rssi_min
        self._running  = False
        self._thread   = None
        self._probes   = {}
        self._device_macs = [
            "11:22:33:44:55:01", "11:22:33:44:55:02",
            "11:22:33:44:55:03", "11:22:33:44:55:04",
            "11:22:33:44:55:05",
        ]

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._mock_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def get_recent_probes(self, max_age_sec: float = 5.0) -> list[WifiProbe]:
        return [WifiProbe(**p) for p in self._probes.values()]

    def clear(self):
        self._probes.clear()

    def _mock_loop(self):
        import random, math
        t = 0.0
        while self._running:
            for i, mac in enumerate(self._device_macs):
                # Simulate RSSI variation based on "position"
                phase = 2 * math.pi * i / len(self._device_macs)
                rssi = int(-55 + 10 * math.sin(t + phase))  # -65 to -45 dBm
                self._probes[mac] = {
                    "mac_address": mac,
                    "rssi": rssi,
                    "ssid": f"Device-{i+1}",
                    "channel": random.choice([1, 6, 11]),
                    "signal_type": 1,
                }
            time.sleep(0.5)
            t += 0.5
