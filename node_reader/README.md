# HOLO-RTLS Node Reader — BlueApro 6/6E WiFi node client (Windows .exe)

Connects to **BlueApro 6/6E** vendor firmware over **UDP, TCP, or HTTP** (user-selected ports).

## Quick start (Windows)

```bash
pip install -r node_reader/requirements.txt
python -m node_reader
```

Build `.exe`:

```bash
pyinstaller node_reader/build.spec
# → dist/HOLO-RTLS-NodeReader.exe
```

## BlueApro setup

| Step | Action |
|------|--------|
| 1 | **Select PC network** — Wi-Fi or Ethernet (same LAN as BlueApro) |
| 2 | Power BlueApro, connect PC to same network |
| 3 | **Scan WiFi nodes** → pick row (e.g. `10.7.15.x` port 80) |
| 4 | Enter **node web password** → **Test node** → **Connect** |
| 5 | **Tags** tab → **Start receiving tags** |

Direct AP mode: `http://192.168.4.1` port **80**

**S/N example:** `261FBLUEAO004`

## Which web UI do you have?

| UI you see | Has Transport menu? | How to send tags to PC |
|------------|---------------------|-------------------------|
| **BlueUp TinyGateway** (Configuration → BLE / transport) | Yes | Raw UDP Client → PC IP:8765 |
| **OpenWrt LuCI** (Network, System, STRATA logo) | **No** | Not in LuCI Network — try AP mode or LuCI → Services |

### BlueUp firmware (Transport / Encoding / Send realtime)

1. Connect PC Wi-Fi to gateway AP: SSID **TinyGateway**, password **tinygateway**
2. Open **http://192.168.4.1** (password **blueup**)
3. **Configuration → Data transport/encoding → Raw UDP Client**
4. Host = PC IP, Port = **8765**, Encoding = JSON Parsed, Send realtime ON

### OpenWrt / STRATA firmware (LuCI screenshots)

LuCI **Network → Interfaces** does **not** configure BLE tag export. Options:

- LuCI → **Services** — look for BLE, MQTT, or scanner packages
- Try BlueUp UI via AP mode (above) if hardware supports both stacks
- Ask vendor how STRATA firmware exports BLE scans (MQTT `rssi/data`, uCentral cloud, etc.)
- **Do not** use System → Logging → External log server (syslog only)

## Transport modes (MQTT recommended for OpenWrt / STRATA WiFi units)

| Transport | Port | Direction |
|-----------|------|-----------|
| **MQTT** (recommended) | **1883** | PC **subscribes** to broker on WiFi unit |
| UDP | 8765 | WiFi unit pushes to PC |
| TCP | 8766 | WiFi unit pushes to PC |
| HTTP push | 8765 | WiFi unit POSTs to PC |
| HTTP pull | 80 | PC GETs node API (often missing) |

### MQTT setup (OpenWrt / STRATA — your unit)

1. Transport = **mqtt**
2. Node / broker IP = **192.168.1.1** (WiFi unit)
3. MQTT port = **1883**
4. Topics = `rssi/data,rssi/raw,ble/rssi,wifi/rssi`
5. **Connect** → Tags → **Start receiving tags**
6. Data log → filter **MQTT** — expect CSV like `NodeMAC,TagMAC,RSSI,Battery`

Payload format: `00:C0:CA:A1:4B:18,F9:2F:B6:2C:DE:24,-72,98`

## Transport modes (UDP / TCP / HTTP)

There is **no industry-standard UDP port** for BLE gateways — pick any free port and use the **same number on BlueApro and PC**.

| Transport | PC port (default) | BlueApro web UI |
|-----------|-------------------|-----------------|
| **UDP** (recommended) | **8765** | Transport → **Raw UDP Client** → Host = PC IP, Port = 8765 |
| **TCP** | **8766** | Transport → **Raw TCP Client** → Host = PC IP, Port = 8766 |
| HTTP push | 8765 | Transport → HTTP → `http://PC_IP:8765/ingest/blueapro` |
| HTTP pull | node port 80 | PC polls node GET API (often missing on vendor firmware) |

**BlueApro settings:** Encoding = **JSON Parsed** (or JSON Raw) · enable **Send realtime** · allow UDP/TCP in **Windows Firewall**.

### Quick UDP setup

1. Select PC network (Ethernet/Wi-Fi) — same LAN as BlueApro
2. Transport = **udp** · PC listen port **8765**
3. **Connect** (starts PC listener)
4. BlueApro web UI → Transport → Raw UDP Client → Host = your PC IP, Port = **8765**
5. Tags tab → **Start receiving tags**

## Tabs

| Tab | Purpose |
|-----|---------|
| **BlueApro Node** | Scan LAN, IP + port, connect, push URI |
| **Tags** | Live tag table, MOKO password per tag |
| **Data log** | NODE / LOCAL / UPLINK traffic |
| **Advanced** | API paths, listen port, central uplink |

## Optional central HOLO-RTLS uplink

Advanced → enable forward → set server host, port, `SCANNER_API_KEY`, anchor MAC.

## Config files

Windows: `%APPDATA%\\HOLO-RTLS\\NodeReader\\`

See `docs/NODE_READER_PLAN.md` for full architecture.
