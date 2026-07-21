# HOLO MQTT Broker — PC broker for WiFi nodes

Simple Windows app (like Mosquitto) — **your PC runs the MQTT broker** and WiFi nodes on the same LAN publish tag data to it.

## Quick start

```bash
pip install -r node_reader/requirements.txt
python -m node_reader
```

Build `.exe`:

```bash
pyinstaller node_reader/build.spec
# → dist/HOLO-MQTT-Broker.exe
```

## Setup (example: PC 10.60.1.5)

| Step | Action |
|------|--------|
| 1 | Select PC network interface (shows your IP, e.g. **10.60.1.5**) |
| 2 | Port **1883** · click **Start broker** |
| 3 | On WiFi node: MQTT broker = **10.60.1.5**, port **1883**, topic **rssi/data** |
| 4 | Watch **MQTT messages** and **Parsed tags** in the app |
| 5 | Windows Firewall: allow **inbound TCP 1883** |

## WiFi node payload

CSV on topic `rssi/data`:

```
00:C0:CA:A1:4B:18,F9:2F:B6:2C:DE:24,-72,98
```

JSON is also supported.

## Config

Windows: `%APPDATA%\HOLO-RTLS\MqttBroker\settings.json`
