# HOLO-RTLS Scanner Node

WiFi + BLE scanning daemon for the HOLO-RTLS indoor positioning system.

## Architecture

```
┌─────────────┐    WiFi probe / BLE ADV    ┌──────────────────────┐
│ Scanner Node │ ─── POST /api/scanner ──→  │  HOLO-RTLS Backend    │
│  (Raspberry  │    detections batch         │  ┌─────────────────┐ │
│    Pi /      │ ←── positions / ack ────   │  │ Trilateration   │ │
│  Laptop)     │                            │  │   Engine        │ │
└─────────────┘                            │  │ (RSSI → metres)  │ │
                                            │  └────────┬────────┘ │
┌─────────────┐    WiFi probe / BLE ADV    │           │          │
│ Scanner Node │ ─── POST /api/scanner ──→  │  ┌────────▼────────┐ │
│  (Node 2)    │    (anchor_mac=NODE2)      │  │  Live Positions  │ │
└─────────────┘                            │  │  + SSE push      │ │
                                            │  └────────┬────────┘ │
                                            │           │          │
                                            │  ┌────────▼────────┐ │
                                            │  │  Frontend Page   │ │
                                            │  │  /tracking       │ │
                                            │  └─────────────────┘ │
                                            └──────────────────────┘
```

## Setup

### 1. Install dependencies

```bash
# Raspberry Pi / Debian / Ubuntu
sudo apt update
sudo apt install python3-pip bluetooth libbluetooth-dev libglib2.0-dev

# Core Python packages
pip3 install requests bleak scapy

# Optional: airmon-ng for WiFi monitor mode (requires compatible adapter)
sudo apt install aircrack-ng
```

### 2. Configure

Create `scanner/config_local.py` (or set environment variables):

```python
# scanner/config_local.py
from scanner.config import ScannerConfig

config = ScannerConfig(
    anchor_mac="AA:BB:CC:DD:EE:01",      # This node's MAC
    backend_url="http://192.168.1.100:5000",
    api_key="your-secret-key",
    wifi_interface="wlan0mon",           # WiFi monitor interface
    scan_interval_sec=1.5,
    tx_power=-40.0,                       # Calibrate after setup
)
```

Environment variables also work:

```bash
export ANCHOR_MAC="AA:BB:CC:DD:EE:01"
export BACKEND_URL="http://192.168.1.100:5000"
export SCANNER_API_KEY="your-secret-key"
export WIFI_INTERFACE="wlan0mon"
```

### 3. Set up WiFi monitor mode

**Option A — Alfa AWUS036NHA (or any Atheros adapter):**
```bash
sudo airmon-ng start wlan0
# → creates wlan0mon
```

**Option B — Raspberry Pi 3/4 built-in WiFi:**
```bash
# Note: Pi inbuilt WiFi doesn't support full monitor mode.
# Use a USB adapter instead.
sudo ip link set wlan0 down
sudo iw dev wlan0 set type monitor
sudo ip link set wlan0 up
```

**Option C — macOS (no WiFi monitor mode via scapy):**
Only BLE scanning will work. WiFi scanning is not available without
a dedicated monitor-mode adapter.

### 4. Set up BLE (Raspberry Pi)

```bash
# Ensure Bluetooth is enabled
sudo systemctl enable bluetooth
sudo systemctl start bluetooth

# Verify adapter
hciconfig
# → should show hci0
```

### 5. Run

```bash
# Development (mock scanners, no hardware)
python3 scanner/main.py --mock

# Production
sudo python3 scanner/main.py

# With custom interface
python3 scanner/main.py --wifi-iface wlan0mon --backend-url http://192.168.1.100:5000
```

### 6. Auto-start on Raspberry Pi

```bash
sudo cp scanner/holo-scanner.service /etc/systemd/system/
sudo systemctl enable holo-scanner
sudo systemctl start holo-scanner

# Check logs
sudo journalctl -u holo-scanner -f
```

## Scanner Service File

Save as `/etc/systemd/system/holo-scanner.service`:

```ini
[Unit]
Description=HOLO-RTLS WiFi/BLE Scanner Node
After=network.target bluetooth.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/holo-rtls
ExecStart=/usr/bin/python3 /opt/holo-rtls/scanner/main.py
Restart=always
RestartSec=10
Environment="ANCHOR_MAC=AA:BB:CC:DD:EE:01"
Environment="BACKEND_URL=http://YOUR_BACKEND:5000"
Environment="SCANNER_API_KEY=your-secret-key"

[Install]
WantedBy=multi-user.target
```

## Calibration

For accurate positioning, each anchor needs its TX power calibrated:

1. **In the `/tracking` frontend page:**
   - Select "Place Anchor" tool → right-click the floor plan to place an anchor
   - Click the anchor → "Calibrate TX Power"

2. **Manual calibration:**
   - Place a reference device (phone/laptop) exactly **1 metre** from the scanner
   - Note the RSSI reading shown in the frontend (or from the scanner logs)
   - POST to calibrate:

```bash
curl -X POST http://localhost:5000/api/scanner/anchors/1/calibrate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reference_rssi": -55.0, "reference_distance": 1.0}'
```

## How Positioning Works

1. **Scanner nodes** continuously scan for WiFi probe requests and BLE advertisements
2. Each node reports detected MACs + RSSI values to the backend every ~1.5 seconds
3. The **backend trilateration engine** collects RSSI readings for each MAC across ≥3 anchors
4. RSSI → distance conversion using the **log-distance path loss model**:
   ```
   distance = 10 ^ ((tx_power - rssi) / (10 × n))
   ```
   where `n` ≈ 2.5 for indoor environments
5. **Least-squares minimisation** solves for (x, y) using the anchor geometry
6. A **Kalman filter** smooths noisy position estimates per device
7. Positions are pushed to the frontend via **Server-Sent Events** (SSE)

## Supported Hardware

| Device | WiFi Scanning | BLE Scanning | Notes |
|--------|--------------|--------------|-------|
| Raspberry Pi 4 + Alfa AWUS036NHA | ✅ Full | ✅ Full | Recommended |
| Raspberry Pi 3 + USB BLE dongle | ❌ (no monitor mode) | ✅ Full | WiFi via BLE only |
| Laptop (Linux) | ✅ With monitor NIC | ✅ | Best for dev |
| Laptop (macOS) | ❌ | ✅ | WiFi via BLE only |
| Laptop (Windows) | ❌ | ✅ (WSL2) | Use WSL2 + USB BT |

## Troubleshooting

**BLE scan fails on Raspberry Pi:**
```bash
sudo hciconfig hci0 up
bluetoothctl
[bluetooth]# power on
[bluetooth]# scan on
```

**WiFi monitor mode fails:**
```bash
# Check for locked interfaces
sudo airmon-ng check kill
```

**Scanner not registering:**
- Verify `SCANNER_API_KEY` matches `backend/config.py` or env var
- Check backend is reachable: `curl http://localhost:5000/api/positioning/live`

**Poor positioning accuracy:**
- Add more anchors (≥3, ideally 4+)
- Ensure anchors are not collinear (spread them out)
- Recalibrate TX power in a quiet environment
- Increase `scan_interval_sec` to 2-3 seconds for more samples per round
