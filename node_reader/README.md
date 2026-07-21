# HOLO-RTLS Node Reader

Standalone Windows/Linux PC app to **test WiFi nodes**, **scan BLE tags** (MOKO H7, iBeacon, Eddystone), and **view raw HTTP/MQTT traffic** to/from the HOLO-RTLS server.

## Quick start

```bash
pip install -r node_reader/requirements.txt
python -m node_reader
```

**Windows .exe:**

```bash
pip install -r node_reader/requirements.txt
pyinstaller node_reader/build.spec
# Output: dist/HOLO-RTLS-NodeReader.exe
```

Requires **Bluetooth ON** on the PC (built-in or USB adapter).

## App tabs

| Tab | Purpose |
|-----|---------|
| **Connection** | Server host/port, HTTP vs MQTT, scanner API key, node list, connect/disconnect |
| **Tags** | Start/stop BLE scan, table of detected tags, edit tag profile + MOKO password |
| **Data log** | Raw traffic: HTTP/MQTT to server, BLE advertisements from tags |

## Admin: configure server for mixed HTTP + MQTT nodes

### 1. Server environment (`.env`)

```env
# HTTP scanner nodes (Pi, PC reader)
SCANNER_API_KEY=your-shared-secret-here

# MQTT broker (ESP32 gateways)
MQTT_BROKER_HOST=192.168.1.100
MQTT_BROKER_PORT=1883
MQTT_USE_TLS=0
```

Every HTTP node must use the **same** `SCANNER_API_KEY`.

### 2. Dashboard → Settings → System

- Set **MQTT Broker Host** (for outbound state sync)

### 3. Dashboard → Hardware Setup

For **MQTT gateways** (ESP32):
- Profile: **ESP32 BLE Gateway** or **Custom MQTT**
- Broker host/port, topic `rssi/data`

For **HTTP nodes** (Raspberry Pi / this PC app):
- No hardware profile needed — they POST to `/api/scanner/detections`

### 4. Dashboard → Anchors / Nodes

Register each physical node:
- Name, MAC address, map position (X/Y)

The PC Node Reader uses **Anchor MAC** as its node identity when forwarding detections.

## Using the PC app as a test node

1. **Connection** tab → enter server IP and HTTP port (`5000`)
2. Transport: **HTTP** (or **MQTT** if broker is configured)
3. Enter **Scanner API key** (matches server `SCANNER_API_KEY`)
4. **Anchor MAC** — auto-filled from PC; or pick a node from **Load nodes from server**
5. **Test connection** → **Connect**
6. **Tags** tab → **Start tag scan** → hold MOKO tag near PC
7. Enable **Forward to server** to push RSSI to HOLO-RTLS live map

## MOKO tag password

MOKO H7 tags use a **BLE configuration password** (same as BeaconX Pro app) — **not** for server login.

- Save password per tag in **Tag settings** (stored locally in `%APPDATA%\HOLO-RTLS\NodeReader\tags.json`)
- Full over-the-air tag programming via GATT requires MOKO protocol support (future enhancement); use BeaconX Pro for slot/beacon/DFU changes today

## Settings file location

| OS | Path |
|----|------|
| Windows | `%APPDATA%\HOLO-RTLS\NodeReader\settings.json` |
| Linux/macOS | `~/.config/HOLO-RTLS/NodeReader/settings.json` |

## Design notes

See `docs/NODE_READER.md` for full UI design, suggested additions, and architecture.
