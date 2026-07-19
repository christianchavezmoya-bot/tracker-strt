#!/usr/bin/env python3
"""
HOLO-RTLS Scanner Node — Main Daemon
Orchestrates WiFi + BLE scanning and reports detections to the backend.

Usage:
  # Production (requires monitor-mode WiFi + BLE adapter)
  python scanner/main.py

  # Development (mock scanners, no hardware needed)
  python scanner/main.py --mock

  # Docker / Raspberry Pi
  docker build -f scanner/Dockerfile . && docker run --net=host \\
      -e ANCHOR_MAC="AA:BB:CC:DD:EE:01" \\
      -e BACKEND_URL="http://192.168.1.100:5000" \\
      holo-rtls-scanner

On Raspberry Pi:
  1. Install dependencies:
     sudo apt install bluetooth libbluetooth-dev
     pip install bleak scapy flask requests
  2. Put WiFi in monitor mode (requires Alfa AWUS036NHA or similar):
     sudo airmon-ng start wlan0
  3. Run:
     sudo python scanner/main.py --wifi-iface wlan0mon

For auto-start on Raspberry Pi:
  sudo cp scanner/holo-scanner.service /etc/systemd/system/
  sudo systemctl enable holo-scanner
  sudo systemctl start holo-scanner
"""
import argparse
import logging
import os
import sys
import time
import threading
import requests

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scanner.config import ScannerConfig
from scanner.wifi_scanner import WifiScanner, MockWifiScanner
from scanner.ble_scanner import BLEScanner, MockBLEScanner

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("scanner")


# ── Main ─────────────────────────────────────────────────────────────────────
class ScannerNode:
    """
    WiFi + BLE scanner daemon.
    Periodically scans, batches detections, POSTs to backend.
    """

    def __init__(self, config: ScannerConfig, mock: bool = False):
        self.config = config
        self.mock   = mock
        self._stop  = threading.Event()

        # ── Choose scanner implementations ────────────────────────────────────
        if mock:
            logger.info("Running in MOCK mode — no real hardware needed")
            self._wifi = MockWifiScanner(rssi_min=config.rssi_min)
            self._ble  = MockBLEScanner(rssi_min=config.rssi_min)
        else:
            self._wifi = WifiScanner(
                interface=config.wifi_interface,
                rssi_min=config.rssi_min,
            )
            self._ble  = BLEScanner(
                adapter=config.ble_adapter,
                rssi_min=config.rssi_min,
                scan_duration=config.ble_scan_duration_sec,
            )

        self._scan_count = 0

    def start(self):
        logger.info(f"Starting scanner node: {self.config.anchor_mac}")
        logger.info(f"Backend: {self.config.backend_url}")

        # Register anchor with backend
        if not self._register_anchor():
            logger.warning("Could not register anchor with backend — continuing anyway")

        self._wifi.start()
        self._ble.start()

        logger.info("Scanner running. Press Ctrl+C to stop.")
        self._main_loop()

    def stop(self):
        logger.info("Stopping scanner node...")
        self._stop.set()
        self._wifi.stop()
        self._ble.stop()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _main_loop(self):
        while not self._stop.is_set():
            try:
                self._scan_count += 1
                detections = self._collect_detections()

                if detections:
                    ok = self._send_detections(detections)
                    if ok:
                        logger.debug(f"Sent {len(detections)} detections to backend")
                    else:
                        logger.warning(f"Failed to send {len(detections)} detections")
                else:
                    logger.debug("No detections this round")

                # Status log every 60 rounds
                if self._scan_count % 60 == 0:
                    wifi_count = len(self._wifi.get_recent_probes())
                    ble_count  = len(self._ble.get_recent_devices())
                    logger.info(
                        f"[{self.config.anchor_mac}] scans={self._scan_count} "
                        f"wifi_probes={wifi_count} ble_devices={ble_count}"
                    )

            except Exception as e:
                logger.error(f"Scan round error: {e}")

            time.sleep(self.config.scan_interval_sec)

    def _collect_detections(self) -> list[dict]:
        """
        Collect all recent WiFi + BLE probes and format for the API.
        Returns a flat list of detection dicts.
        """
        detections = []

        # WiFi probes
        for probe in self._wifi.get_recent_probes(max_age_sec=3.0):
            if self.config.should_ignore(probe.mac_address):
                continue
            detections.append({
                "mac_address": probe.mac_address.upper(),
                "rssi": probe.rssi,
                "signal_type": 1,   # WiFi
                "ssid": probe.ssid,
                "channel": probe.channel,
            })

        # BLE advertisements
        for dev in self._ble.get_recent_devices(max_age_sec=3.0):
            if self.config.should_ignore(dev.mac_address):
                continue
            detections.append({
                "mac_address": dev.mac_address.upper(),
                "rssi": dev.rssi,
                "signal_type": 2,   # BLE
                "adv_name": dev.adv_name,
            })

        return detections

    def _send_detections(self, detections: list[dict]) -> bool:
        """POST detections to the backend."""
        url = f"{self.config.backend_url}/api/scanner/detections"
        headers = {
            "Content-Type": "application/json",
            "X-Scanner-Key": self.config.api_key,
        }
        payload = {
            "anchor_mac": self.config.anchor_mac,
            "detections": detections,
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            return resp.status_code in (200, 201)
        except requests.RequestException as e:
            logger.debug(f"Backend unreachable: {e}")
            return False

    def _register_anchor(self) -> bool:
        """Register this scanner node as an anchor in the backend."""
        url = f"{self.config.backend_url}/api/scanner/anchors"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",  # scanner uses api_key as Bearer
        }
        # Try unauthenticated first (for convenience)
        try:
            resp = requests.post(
                url,
                json={
                    "mac_address": self.config.anchor_mac,
                    "name": f"Scanner-{self.config.anchor_mac[-5:].replace(':','')}",
                },
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            return resp.status_code in (200, 201)
        except requests.RequestException:
            return False


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="HOLO-RTLS Scanner Node")
    parser.add_argument("--mock", action="store_true",
                        help="Use mock scanners (no hardware needed)")
    parser.add_argument("--wifi-iface", default=None,
                        help="WiFi interface in monitor mode (default: from config)")
    parser.add_argument("--backend-url", default=None,
                        help="Backend URL (default: from config/env)")
    parser.add_argument("--anchor-mac", default=None,
                        help="This scanner's MAC address (default: from config/env)")
    args = parser.parse_args()

    # Load config
    try:
        from scanner.config_local import ScannerConfig as LocalConfig
        config = LocalConfig()
    except ImportError:
        config = ScannerConfig()

    # CLI overrides
    if args.mock:
        config.scan_interval_sec = 1.0
    if args.wifi_iface:
        config.wifi_interface = args.wifi_iface
    if args.backend_url:
        config.backend_url = args.backend_url
    if args.anchor_mac:
        config.anchor_mac = args.anchor_mac

    node = ScannerNode(config, mock=args.mock)

    try:
        node.start()
    except KeyboardInterrupt:
        print()
        logger.info("Interrupted by user")
    finally:
        node.stop()
        logger.info("Scanner node shut down cleanly.")


if __name__ == "__main__":
    main()
