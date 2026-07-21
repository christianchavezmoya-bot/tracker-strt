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

## Transport modes (most BlueApro units use UDP or TCP)

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
