"""
HOLO-RTLS Scanner Node — Configuration
Copy this to config_local.py and fill in your values.
"""
import os
from dataclasses import dataclass, field


@dataclass
class ScannerConfig:
    # ── Identity ────────────────────────────────────────────────────────────────
    # The MAC address of THIS scanner node (used as anchor identifier)
    # Run `ip link show` or `getmac` to find it
    anchor_mac: str = os.getenv("ANCHOR_MAC", "AA:BB:CC:DD:EE:01")

    # ── Backend ────────────────────────────────────────────────────────────────
    backend_url: str = os.getenv("BACKEND_URL", "http://localhost:5000")
    api_key: str     = os.getenv("SCANNER_API_KEY", "scanner-dev-key")

    # ── Scanning ───────────────────────────────────────────────────────────────
    # Scan interval in seconds
    scan_interval_sec: float = 1.5
    # WiFi: interface in monitor mode (e.g. "wlan0mon")
    wifi_interface: str = os.getenv("WIFI_INTERFACE", "wlan0")
    # BLE: adapter name (None = default)
    ble_adapter: str = os.getenv("BLE_ADAPTER", None)
    # Ignore detections weaker than this (dBm)
    rssi_min: int = -90
    # BLE scan duration per round (seconds)
    ble_scan_duration_sec: float = 1.0

    # ── Filter ────────────────────────────────────────────────────────────────
    # Set of MAC prefixes to ignore (mobile phones often start with known prefixes)
    # Format: uppercase, colon-separated
    ignore_prefixes: list = field(default_factory=lambda: [
        "FC:A6:67",  # Samsung
        "A4:77:33",  # Google
        "D8:BB:2C",  # Apple
        "40:B0:34",  # Apple
        "18:AF:61",  # Apple
        "28:CF:DA",  # Apple
        "7C:C3:A1",  # Apple
        "AC:BC:32",  # Apple
        "94:94:26",  # Apple
        "64:20:0C",  # Apple
        "9C:04:EB",  # Apple
        "F4:F5:D8",  # Apple
        "24:A0:74",  # Apple
        "E8:7C:3C",  # Apple
        "C0:9F:42",  # Apple
        "88:C6:63",  # Apple
        "68:96:7B",  # Apple
        "54:72:4F",  # Samsung
        "24:4B:FE",  # Samsung
        "E4:0A:1D",  # Samsung
        "9C:35:EB",  # Samsung
        "B0:07:D9",  # Samsung
    ])

    # ── Hardware TX power (dBm at 1 metre) — set after calibration ─────────────
    tx_power: float = -40.0

    def __post_init__(self):
        self.anchor_mac = self.anchor_mac.upper().replace("-", ":")

    @property
    def ignore_set(self) -> set:
        return {p.upper().replace("-", ":") for p in self.ignore_prefixes}

    def should_ignore(self, mac: str) -> bool:
        mac = mac.upper().replace("-", ":")
        for prefix in self.ignore_set:
            if mac.startswith(prefix):
                return True
        return False
