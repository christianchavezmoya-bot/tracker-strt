# HOLO-RTLS — Hardware Configuration Guide

> **Purpose:** Configure real UWB, BLE, WiFi, and environmental sensors.
> Access via: **Dashboard → Hardware Setup** (or `/hardware`)

---

## Architecture: How Hardware Connects

```
Physical Device (UWB tag, BLE beacon, etc.)
        │
        ▼
 Hardware Config (stored in DB)
        │
        ▼
 Positioning Service (reads hardware config, connects to device)
        │
        ▼
 MQTT Broker / Serial Reader → Position Data
        │
        ▼
 HOLO-RTLS Web App (real-time display)
```

Every hardware connection is stored as a **HardwareConfig** row in SQLite.
The positioning service reads all active configs on startup and connects automatically.
If a device goes offline, it marks the config as ERROR and logs the error message.

---

## Supported Hardware Profiles

### UWB — Ultra-Wideband (highest accuracy: 10–30cm)

| Profile | Vendor | Protocol | Notes |
|---|---|---|---|
| Qorvo DWM1001 | Qorvo | Serial | Most common. UWB + BLE combo. TDoA + TWR. |
| DecaWave DW1000 | DecaWave | Serial | Original DW1000. Requires external MCU. |
| DecaWave DW3000 | Qorvo | Serial | Next-gen. Lower power, faster data rate. |
| Sewio RTLS | Sewio | MQTT | Enterprise system. Publishes to MQTT broker. |
| Pozyx Creator | Pozyx | Serial | Arduino-compatible. Good for prototyping. |
| Custom MQTT | Any | MQTT | Universal. Map any JSON/CSV payload to HOLO-RTLS fields. |
| Mock / Simulator | HOLO-RTLS | — | Test without hardware. Generates synthetic data. |

### BLE — Bluetooth Low Energy (accuracy: 3–10m)

| Profile | Vendor | Protocol | Notes |
|---|---|---|---|
| Generic iBeacon | Various | BLE GATT | Standard beacon format. UUID + Major + Minor. |
| Ruuvi Tag | Ruuvi | BLE GATT | Temp + humidity + pressure + accelerometer. |
| ESP32 BLE Gateway | Espressif | MQTT | ESP32 as BLE scanner, publishes RSSI to MQTT. |

### WiFi RSSI (accuracy: 5–15m)

| Profile | Vendor | Protocol | Notes |
|---|---|---|---|
| ESP32 WiFi Scanner | Espressif | MQTT | Detects nearby APs + mobile devices. |

### Environmental Sensors

| Profile | Vendor | Protocol | Notes |
|---|---|---|---|
| Sensirion SEN5x | Sensirion | I2C | PM2.5, VOC, NO2, temp, humidity. Air quality zones. |

---

## Quick Start: Adding Hardware

### Step 1 — Open Hardware Setup

```
Dashboard → click your name (top right) → Hardware Setup
```

### Step 2 — Add a Configuration

1. Click **"+ Add Hardware Configuration"**
2. Select your hardware **profile** (e.g. Qorvo DWM1001)
3. Fill in the required settings (port, baud rate, etc.)
4. Click **"Test Connection"** to verify
5. Click **"Save"** — the device is now configured

### Step 3 — Connect

After saving, the device appears in your list. Click the **green power button**
to connect. On app restart, all active configs reconnect automatically.

---

## Per-Profile Setup Instructions

### Qorvo DWM1001 (Serial)

```
Required: USB-UART bridge (CP2102), DWM1001 module, power
1. Flash DWM1001 with tag firmware (see Qorvo documentation)
2. Connect via USB to your server
3. In HOLO-RTLS:
   - Profile: Qorvo DWM1001
   - Port: /dev/ttyUSB0  (Linux) or COM3 (Windows)
   - Baud Rate: 115200
   - Channel: 5 (default)
   - Firmware: tag
4. Click Test Connection → Save → Connect
```

### Sewio RTLS (MQTT)

```
Required: Sewio MQTT broker IP + credentials
1. Note your Sewio broker host and topic
2. In HOLO-RTLS:
   - Profile: Sewio RTLS
   - Broker Host: 192.168.1.100
   - Broker Port: 1883
   - Topic: rtls/positions  (match your Sewio config)
   - Username/Password: from Sewio admin panel
3. Click Test Connection → Save → Connect
```

### Generic iBeacon (BLE)

```
Required: BLE scanner gateway (ESP32 or Raspberry Pi + BLE adapter)
1. Flash ESP32 with BLE gateway firmware (see Espressif examples)
2. ESP32 must publish to your MQTT broker
3. In HOLO-RTLS:
   - Profile: Generic iBeacon
   - Configure RSSI threshold (e.g. -90 dBm to filter weak signals)
4. The positioning engine will use RSSI → distance conversion
```

### Custom MQTT (Universal)

```
Use this for any device that publishes JSON or CSV to MQTT.
Required: broker credentials + topic + field mapping

Example payload from your device:
{
  "mac": "AA:BB:CC:DD:EE:FF",
  "x": 12.5,
  "y": 8.3,
  "z": 0.0,
  "rssi": -72
}

Field mapping in HOLO-RTLS:
{
  "tag_id": "mac",
  "x": "x",
  "y": "y",
  "z": "z",
  "rssi": "rssi"
}

The positioning engine maps your field names → HOLO-RTLS fields automatically.
```

### Mock / Simulator

```
No hardware needed. Generates synthetic UWB position data.
- Useful for development without physical devices
- Useful for demo / training
- Configurable: number of tags, anchors, noise level, movement pattern
```

---

## BLE Installation (Linux/Raspberry Pi)

```bash
# Install system BLE dependencies
sudo apt update
sudo apt install bluez libbluetooth-dev

# Install Python BLE libraries
pip install bleak pybluez bluepy

# Verify Bluetooth adapter
hciconfig
# Should show hci0 device
```

---

## Connection Status

| Status | Meaning |
|---|---|
| **DISCONNECTED** | Device not connected. Click power button to connect. |
| **CONNECTING** | Attempting connection. |
| **CONNECTED** | Live data flowing. |
| **ERROR** | Connection failed. Check error message. Hover the status dot. |

---

## Position Calculation

```
RSSI or UWB ranges
       │
       ▼
  Trilateration  ← Uses reference/uwb_positioning.py
       │
       ▼
  Kalman Filter   ← Smooths position (reference/uwb_positioning.py)
       │
       ▼
  Coordinate Transform  ← Uses reference/floor_plan_mapper.py
       │
       ▼
  Database Write + SSE Broadcast
       │
       ▼
  Web UI (real-time dots on map)
```

The positioning engine is **profile-aware**. UWB profiles use
range-based trilateration (most accurate). BLE/WiFi profiles use
RSSI → distance conversion + weighted centroid.

---

## Adding a New Hardware Profile

To add a new device profile, edit `backend/models/hardware_profiles.py`:

```python
@profile(
    id="my_device_id",
    name="My Device Name",
    vendor="Vendor Name",
    hardware_type=HardwareType.UWB,    # UWB, BLE, WIFI, or ENVIRO
    protocol=Protocol.MQTT,            # MQTT, SERIAL, REST, WEBSOCKET, BLE_GATT
    description="Short description...",
    connection_help="How to connect physically...",
    settings_fields=[
        _field("host", "Server Host", "string", required=True, default="192.168.1.1"),
        _field("port", "Port",         "int",    required=True, default="1883"),
    ],
    example_settings={"host": "192.168.1.1", "port": 1883},
)
def my_device():
    pass
```

The profile appears automatically in the Hardware Setup page — no frontend changes needed.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Serial port not found | Check port path: `/dev/ttyUSB0` vs `/dev/ttyACM0`. On Windows use `COM3`. |
| MQTT connection refused | Verify broker IP, port, username/password. Check firewall. |
| BLE not scanning | `sudo hciconfig hci0 up` to bring up the adapter. |
| No position data | Check that the device is broadcasting. For UWB: ensure at least 3 anchors are active. |
| Stale position data | Check that the device hasn't gone offline. Look at "Last Seen" in the details panel. |

---

## Next: Phase 3 — Positioning Engine

After hardware is configured, wire the `PositioningService` to read active configs
and feed live data into the SSE stream. See `docs/PHASE_3_TODO.md` (to be written).
