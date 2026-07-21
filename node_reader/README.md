# HOLO-RTLS Node Reader — BlueApro 6/6E WiFi node client (Windows .exe)

Connects to **BlueApro 6/6E** vendor firmware over **HTTP** (user-selected port).

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
| 1 | Power BlueApro, connect PC to its WiFi (or same LAN) |
| 2 | Default AP: `http://192.168.4.1` port **80** |
| 3 | Set web UI password in BlueApro system menu |
| 4 | In Node Reader: enter IP, **port**, username/password → **Test** → **Connect** |

**S/N example:** `261FBLUEAO004`

## HTTP modes

### Pull (default) — PC → node GET

PC polls the node API for BLE devices. Configure API paths in **Advanced** if vendor firmware differs.

### Push — node POST → PC

BlueApro vendor firmware often sends scan data as HTTP **client**:

1. Node Reader shows URI: `http://YOUR_PC_IP:8765/ingest/blueapro`
2. In BlueApro web UI → **Transport → HTTP** → set that URI
3. Select **Push** mode in app → **Connect**
4. Tags appear when node POSTs data

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
