#!/usr/bin/env python3
"""
HOLO-RTLS Node Reader — standalone PC app for WiFi node testing and BLE tag discovery.

Usage:
  python -m node_reader.app
  python node_reader/app.py

Build Windows .exe:
  pip install -r node_reader/requirements.txt
  pyinstaller node_reader/build.spec
"""
from __future__ import annotations

import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

# Allow running as script or module
_ROOT = __file__.replace("\\", "/").rsplit("/", 2)[0]
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT.rsplit("/", 1)[0] if _ROOT.endswith("node_reader") else _ROOT)

from node_reader.ble_engine import BLEScanEngine, TagDetection
from node_reader.config_store import (
    AppConfig,
    TagProfile,
    load_config,
    load_tag_profiles,
    save_config,
    save_tag_profiles,
)
from node_reader.tag_classifier import SCAN_TYPE_LABELS
from node_reader.transport import ServerTransport, scan_network_for_servers


def _local_mac() -> str:
    try:
        import uuid
        n = uuid.getnode()
        return ":".join(f"{(n >> ele) & 0xFF:02X}" for ele in range(40, -1, -8))
    except Exception:
        return "PC:READER:01"


class NodeReaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("HOLO-RTLS Node Reader")
        self.geometry("980x640")
        self.minsize(860, 520)

        self.cfg = load_config()
        self.tag_profiles = load_tag_profiles()
        self.transport = ServerTransport(log=self._log_message)
        self.ble = BLEScanEngine(rssi_min=self.cfg.rssi_min, tags_only=self.cfg.tags_only)
        self.ble.on_update = self._on_ble_update

        self._scanning = False
        self._forward_job = None
        self._data_log: list[tuple[str, str, str, str]] = []

        self._build_ui()
        self._load_form_from_config()
        if not self.cfg.anchor_mac:
            self.var_anchor_mac.set(_local_mac())

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.tab_conn = ttk.Frame(nb)
        self.tab_tags = ttk.Frame(nb)
        self.tab_data = ttk.Frame(nb)
        nb.add(self.tab_conn, text="  Connection  ")
        nb.add(self.tab_tags, text="  Tags  ")
        nb.add(self.tab_data, text="  Data log  ")

        self._build_connection_tab()
        self._build_tags_tab()
        self._build_data_tab()

        self.status = ttk.Label(self, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self.status.pack(fill=tk.X, side=tk.BOTTOM, padx=8, pady=(0, 6))

    def _build_connection_tab(self) -> None:
        f = self.tab_conn
        pad = {"padx": 8, "pady": 4}

        # Server
        srv = ttk.LabelFrame(f, text="HOLO-RTLS Server")
        srv.pack(fill=tk.X, **pad)

        row0 = ttk.Frame(srv)
        row0.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(row0, text="Server host:").pack(side=tk.LEFT)
        self.var_host = tk.StringVar()
        ttk.Entry(row0, textvariable=self.var_host, width=22).pack(side=tk.LEFT, padx=6)
        ttk.Label(row0, text="HTTP port:").pack(side=tk.LEFT, padx=(12, 0))
        self.var_server_port = tk.IntVar(value=5000)
        ttk.Entry(row0, textvariable=self.var_server_port, width=8).pack(side=tk.LEFT, padx=6)
        ttk.Button(row0, text="Scan network", command=self._scan_network).pack(side=tk.LEFT, padx=8)

        row1 = ttk.Frame(srv)
        row1.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(row1, text="Transport:").pack(side=tk.LEFT)
        self.var_transport = tk.StringVar(value="http")
        ttk.Radiobutton(row1, text="HTTP (direct)", variable=self.var_transport, value="http").pack(
            side=tk.LEFT, padx=6
        )
        ttk.Radiobutton(row1, text="MQTT", variable=self.var_transport, value="mqtt").pack(
            side=tk.LEFT, padx=6
        )
        ttk.Label(row1, text="MQTT port:").pack(side=tk.LEFT, padx=(16, 0))
        self.var_mqtt_port = tk.IntVar(value=1883)
        ttk.Entry(row1, textvariable=self.var_mqtt_port, width=8).pack(side=tk.LEFT, padx=6)
        self.var_mqtt_tls = tk.BooleanVar(value=False)
        ttk.Checkbutton(row1, text="TLS", variable=self.var_mqtt_tls).pack(side=tk.LEFT, padx=4)

        row2 = ttk.Frame(srv)
        row2.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(row2, text="Scanner API key:").pack(side=tk.LEFT)
        self.var_api_key = tk.StringVar()
        ttk.Entry(row2, textvariable=self.var_api_key, width=36, show="*").pack(side=tk.LEFT, padx=6)
        ttk.Label(row2, text="MQTT topic:").pack(side=tk.LEFT, padx=(8, 0))
        self.var_mqtt_topic = tk.StringVar(value="rssi/data")
        ttk.Entry(row2, textvariable=self.var_mqtt_topic, width=18).pack(side=tk.LEFT, padx=6)

        # Node identity
        node = ttk.LabelFrame(f, text="WiFi Node (this PC acts as a scanner node)")
        node.pack(fill=tk.X, **pad)

        row3 = ttk.Frame(node)
        row3.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(row3, text="Anchor MAC:").pack(side=tk.LEFT)
        self.var_anchor_mac = tk.StringVar()
        ttk.Entry(row3, textvariable=self.var_anchor_mac, width=20).pack(side=tk.LEFT, padx=6)
        ttk.Label(row3, text="Node name:").pack(side=tk.LEFT, padx=(12, 0))
        self.var_anchor_name = tk.StringVar()
        ttk.Entry(row3, textvariable=self.var_anchor_name, width=24).pack(side=tk.LEFT, padx=6)

        row4 = ttk.Frame(node)
        row4.pack(fill=tk.X, padx=8, pady=4)
        ttk.Button(row4, text="Load nodes from server", command=self._load_nodes_from_server).pack(
            side=tk.LEFT
        )
        ttk.Label(row4, text="Admin email:").pack(side=tk.LEFT, padx=(12, 0))
        self.var_admin_email = tk.StringVar()
        ttk.Entry(row4, textvariable=self.var_admin_email, width=22).pack(side=tk.LEFT, padx=4)
        ttk.Label(row4, text="Password:").pack(side=tk.LEFT)
        self.var_admin_password = tk.StringVar()
        ttk.Entry(row4, textvariable=self.var_admin_password, width=16, show="*").pack(side=tk.LEFT, padx=4)

        # Node picker
        pick = ttk.LabelFrame(f, text="Registered nodes (select to test)")
        pick.pack(fill=tk.BOTH, expand=True, **pad)
        cols = ("name", "mac", "status", "pos")
        self.node_tree = ttk.Treeview(pick, columns=cols, show="headings", height=6)
        for c, w in zip(cols, (140, 160, 80, 180)):
            self.node_tree.heading(c, text=c.title())
            self.node_tree.column(c, width=w)
        self.node_tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        self.node_tree.bind("<<TreeviewSelect>>", self._on_node_select)

        # Actions
        act = ttk.Frame(f)
        act.pack(fill=tk.X, **pad)
        ttk.Button(act, text="Test connection", command=self._test_connection).pack(side=tk.LEFT, padx=4)
        self.btn_connect = ttk.Button(act, text="Connect", command=self._toggle_connect)
        self.btn_connect.pack(side=tk.LEFT, padx=4)
        ttk.Button(act, text="Save settings", command=self._save_settings).pack(side=tk.LEFT, padx=4)
        self.lbl_conn_state = ttk.Label(act, text="● Disconnected", foreground="#c44")
        self.lbl_conn_state.pack(side=tk.RIGHT, padx=8)

    def _build_tags_tab(self) -> None:
        f = self.tab_tags
        pad = {"padx": 8, "pady": 4}

        bar = ttk.Frame(f)
        bar.pack(fill=tk.X, **pad)
        self.btn_scan = ttk.Button(bar, text="▶ Start tag scan", command=self._toggle_scan)
        self.btn_scan.pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Clear list", command=self._clear_tags).pack(side=tk.LEFT, padx=4)
        self.var_tags_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Tags only (hide phones)", variable=self.var_tags_only).pack(
            side=tk.LEFT, padx=8
        )
        self.var_forward = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Forward to server when connected", variable=self.var_forward).pack(
            side=tk.LEFT, padx=8
        )
        self.lbl_scan_state = ttk.Label(bar, text="Scan stopped")
        self.lbl_scan_state.pack(side=tk.RIGHT, padx=8)

        paned = ttk.PanedWindow(f, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, **pad)

        left = ttk.Frame(paned)
        paned.add(left, weight=3)
        cols = ("mac", "name", "rssi", "type", "strength")
        self.tag_tree = ttk.Treeview(left, columns=cols, show="headings")
        for c, w in zip(cols, (140, 120, 60, 100, 70)):
            self.tag_tree.heading(c, text=c.upper())
            self.tag_tree.column(c, width=w)
        self.tag_tree.pack(fill=tk.BOTH, expand=True)
        self.tag_tree.bind("<<TreeviewSelect>>", self._on_tag_select)

        right = ttk.LabelFrame(paned, text="Tag settings")
        paned.add(right, weight=2)
        self._tag_detail_vars = {}
        row = 0
        ttk.Label(right, text="MAC address:").grid(row=row, column=0, sticky=tk.W, padx=8, pady=4)
        self._tag_detail_vars["mac"] = tk.StringVar()
        ttk.Entry(right, textvariable=self._tag_detail_vars["mac"], width=32, state="readonly").grid(
            row=row, column=1, sticky=tk.EW, padx=8, pady=4
        )
        row += 1
        ttk.Label(right, text="Display name:").grid(row=row, column=0, sticky=tk.W, padx=8, pady=4)
        self._tag_detail_vars["display_name"] = tk.StringVar()
        ttk.Entry(right, textvariable=self._tag_detail_vars["display_name"], width=32).grid(
            row=row, column=1, sticky=tk.EW, padx=8, pady=4
        )
        row += 1
        ttk.Label(right, text="Scan type:").grid(row=row, column=0, sticky=tk.W, padx=8, pady=4)
        self._tag_detail_vars["scan_type"] = tk.StringVar()
        self.cmb_scan_type = ttk.Combobox(
            right,
            textvariable=self._tag_detail_vars["scan_type"],
            values=list(SCAN_TYPE_LABELS.keys()),
            state="readonly",
            width=30,
        )
        self.cmb_scan_type.grid(row=row, column=1, sticky=tk.EW, padx=8, pady=4)
        row += 1
        ttk.Label(right, text="MOKO password:").grid(row=row, column=0, sticky=tk.W, padx=8, pady=4)
        self._tag_detail_vars["moko_password"] = tk.StringVar()
        ttk.Entry(right, textvariable=self._tag_detail_vars["moko_password"], width=32, show="*").grid(
            row=row, column=1, sticky=tk.EW, padx=8, pady=4
        )
        row += 1
        ttk.Label(right, text="Notes:").grid(row=row, column=0, sticky=tk.W, padx=8, pady=4)
        self._tag_detail_vars["notes"] = tk.StringVar()
        ttk.Entry(right, textvariable=self._tag_detail_vars["notes"], width=32).grid(
            row=row, column=1, sticky=tk.EW, padx=8, pady=4
        )
        row += 1

        ttk.Label(right, text="Beacon / raw:").grid(row=row, column=0, sticky=tk.NW, padx=8, pady=4)
        self.txt_beacon = tk.Text(right, height=6, width=40, font=("Consolas", 9))
        self.txt_beacon.grid(row=row, column=1, sticky=tk.NSEW, padx=8, pady=4)
        right.rowconfigure(row, weight=1)
        right.columnconfigure(1, weight=1)
        row += 1

        ttk.Button(right, text="Save tag profile", command=self._save_tag_profile).grid(
            row=row, column=1, sticky=tk.E, padx=8, pady=8
        )
        row += 1
        ttk.Label(
            right,
            text="MOKO password is used when configuring the tag over BLE\n(same as BeaconX Pro app). Stored locally only.",
            font=("TkDefaultFont", 8),
            foreground="#666",
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=8, pady=4)

    def _build_data_tab(self) -> None:
        f = self.tab_data
        pad = {"padx": 8, "pady": 4}
        bar = ttk.Frame(f)
        bar.pack(fill=tk.X, **pad)
        ttk.Label(bar, text="Filter:").pack(side=tk.LEFT)
        self.var_log_filter = tk.StringVar(value="ALL")
        for val in ("ALL", "HTTP", "MQTT", "BLE"):
            ttk.Radiobutton(bar, text=val, variable=self.var_log_filter, value=val, command=self._refresh_log_view).pack(
                side=tk.LEFT, padx=4
            )
        ttk.Button(bar, text="Clear log", command=self._clear_log).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bar, text="Export log", command=self._export_log).pack(side=tk.RIGHT, padx=4)

        self.txt_log = tk.Text(f, font=("Consolas", 9), wrap=tk.NONE)
        self.txt_log.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        sb = ttk.Scrollbar(f, orient=tk.VERTICAL, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb.set)

        ttk.Label(
            f,
            text="Shows traffic TO/FROM server (HTTP/MQTT) and BLE advertisements seen by this PC.",
            font=("TkDefaultFont", 8),
            foreground="#666",
        ).pack(anchor=tk.W, padx=8, pady=4)

    # ── Config ────────────────────────────────────────────────────────────────

    def _load_form_from_config(self) -> None:
        c = self.cfg
        self.var_host.set(c.server_host)
        self.var_server_port.set(c.server_port)
        self.var_transport.set(c.transport)
        self.var_mqtt_port.set(c.mqtt_port)
        self.var_mqtt_tls.set(c.mqtt_use_tls)
        self.var_mqtt_topic.set(c.mqtt_topic)
        self.var_api_key.set(c.scanner_api_key)
        self.var_anchor_mac.set(c.anchor_mac or _local_mac())
        self.var_anchor_name.set(c.anchor_name)
        self.var_admin_email.set(c.admin_email)
        self.var_admin_password.set(c.admin_password)
        self.var_tags_only.set(c.tags_only)
        self.var_forward.set(c.forward_to_server)
        for node in c.saved_nodes:
            self._add_node_row(node)

    def _save_settings(self) -> None:
        self.cfg.server_host = self.var_host.get().strip()
        self.cfg.server_port = int(self.var_server_port.get())
        self.cfg.transport = self.var_transport.get()
        self.cfg.mqtt_port = int(self.var_mqtt_port.get())
        self.cfg.mqtt_use_tls = bool(self.var_mqtt_tls.get())
        self.cfg.mqtt_topic = self.var_mqtt_topic.get().strip()
        self.cfg.scanner_api_key = self.var_api_key.get()
        self.cfg.anchor_mac = self.var_anchor_mac.get().strip().upper()
        self.cfg.anchor_name = self.var_anchor_name.get().strip()
        self.cfg.admin_email = self.var_admin_email.get().strip()
        self.cfg.admin_password = self.var_admin_password.get()
        self.cfg.tags_only = bool(self.var_tags_only.get())
        self.cfg.forward_to_server = bool(self.var_forward.get())
        save_config(self.cfg)
        self._set_status("Settings saved")
        messagebox.showinfo("Saved", f"Settings saved to config folder.")

    # ── Connection actions ────────────────────────────────────────────────────

    def _scan_network(self) -> None:
        self._set_status("Scanning local network for HOLO-RTLS servers…")
        port = int(self.var_server_port.get())

        def work() -> None:
            found = scan_network_for_servers(port=port)
            self.after(0, lambda: self._network_scan_done(found))

        threading.Thread(target=work, daemon=True).start()

    def _network_scan_done(self, hosts: list[str]) -> None:
        if not hosts:
            messagebox.showinfo("Network scan", "No servers found on HTTP port. Enter host manually.")
            self._set_status("Network scan: no hosts found")
            return
        if len(hosts) == 1:
            self.var_host.set(hosts[0])
        else:
            dlg = tk.Toplevel(self)
            dlg.title("Select server")
            ttk.Label(dlg, text="Servers found on your network:").pack(padx=12, pady=8)
            lb = tk.Listbox(dlg, height=min(8, len(hosts)))
            for h in hosts:
                lb.insert(tk.END, h)
            lb.pack(padx=12, pady=4)

            def pick() -> None:
                sel = lb.curselection()
                if sel:
                    self.var_host.set(hosts[sel[0]])
                dlg.destroy()

            ttk.Button(dlg, text="Use selected", command=pick).pack(pady=8)
        self._set_status(f"Found {len(hosts)} server(s)")

    def _load_nodes_from_server(self) -> None:
        host = self.var_host.get().strip()
        port = int(self.var_server_port.get())
        email = self.var_admin_email.get().strip()
        password = self.var_admin_password.get()
        if not email or not password:
            messagebox.showwarning("Login required", "Enter admin email and password to load nodes.")
            return
        res = self.transport.login(host, port, email, password)
        if not res.ok:
            messagebox.showerror("Login failed", res.message + "\n" + res.detail)
            return
        nodes, err = self.transport.fetch_nodes(host, port)
        if err:
            messagebox.showerror("Error", err)
            return
        for i in self.node_tree.get_children():
            self.node_tree.delete(i)
        self.cfg.saved_nodes = []
        for n in nodes:
            self._add_node_row(n)
            self.cfg.saved_nodes.append(n)
        save_config(self.cfg)
        self._set_status(f"Loaded {len(nodes)} node(s) from server")

    def _add_node_row(self, n: dict) -> None:
        name = n.get("assigned_name") or n.get("name") or "Node"
        mac = n.get("mac_address") or n.get("mac") or ""
        status = n.get("status_label") or str(n.get("status", ""))
        pos = f"{n.get('pos_x', 0):.1f}, {n.get('pos_y', 0):.1f}"
        self.node_tree.insert("", tk.END, values=(name, mac, status, pos), iid=mac or name)

    def _on_node_select(self, _evt=None) -> None:
        sel = self.node_tree.selection()
        if not sel:
            return
        vals = self.node_tree.item(sel[0], "values")
        if len(vals) >= 2 and vals[1]:
            self.var_anchor_mac.set(vals[1])
        if vals:
            self.var_anchor_name.set(vals[0])

    def _test_connection(self) -> None:
        host = self.var_host.get().strip()
        port = int(self.var_server_port.get())
        transport = self.var_transport.get()
        api_key = self.var_api_key.get()
        if transport == "http":
            res = self.transport.test_http(host, port, api_key)
        else:
            res = self.transport.connect(
                host, port, "mqtt",
                int(self.var_mqtt_port.get()),
                bool(self.var_mqtt_tls.get()),
                self.var_mqtt_topic.get(),
                api_key="",  # mqtt user optional — extend later
            )
            if res.ok:
                self.transport.disconnect()
        if res.ok:
            messagebox.showinfo("Test OK", res.message)
        else:
            messagebox.showerror("Test failed", res.message + "\n" + res.detail)
        self._set_status(res.message)

    def _toggle_connect(self) -> None:
        if self.transport.is_connected:
            self.transport.disconnect()
            self.btn_connect.configure(text="Connect")
            self.lbl_conn_state.configure(text="● Disconnected", foreground="#c44")
            self._set_status("Disconnected")
            self._stop_forward_loop()
            return
        host = self.var_host.get().strip()
        port = int(self.var_server_port.get())
        res = self.transport.connect(
            host,
            port,
            self.var_transport.get(),
            int(self.var_mqtt_port.get()),
            bool(self.var_mqtt_tls.get()),
            self.var_mqtt_topic.get(),
            api_key=self.var_api_key.get(),
        )
        if res.ok:
            self.btn_connect.configure(text="Disconnect")
            self.lbl_conn_state.configure(text="● Connected", foreground="#2a8")
            self._set_status(res.message)
            if self.var_forward.get():
                self._start_forward_loop()
        else:
            messagebox.showerror("Connect failed", res.message + "\n" + res.detail)

    # ── Tag scan ──────────────────────────────────────────────────────────────

    def _toggle_scan(self) -> None:
        if self._scanning:
            self._stop_scan()
        else:
            self._start_scan()

    def _start_scan(self) -> None:
        self.ble.rssi_min = self.cfg.rssi_min
        self.ble.tags_only = bool(self.var_tags_only.get())
        self.ble.start()
        self._scanning = True
        self.btn_scan.configure(text="■ Stop tag scan")
        self.lbl_scan_state.configure(text="Scanning BLE…")
        self._set_status("BLE tag scan started — bring MOKO tag near PC")

    def _stop_scan(self) -> None:
        self._scanning = False
        self.ble.stop()
        self.btn_scan.configure(text="▶ Start tag scan")
        self.lbl_scan_state.configure(text="Scan stopped")

    def _clear_tags(self) -> None:
        self.ble.clear()
        for i in self.tag_tree.get_children():
            self.tag_tree.delete(i)

    def _on_ble_update(self, det: TagDetection, is_new: bool) -> None:
        self.after(0, lambda: self._upsert_tag_row(det))
        self._log_message("IN", "BLE", f"{det.mac} {det.rssi} dBm {det.name or 'Unknown'}")

    def _upsert_tag_row(self, det: TagDetection) -> None:
        vals = (
            det.mac,
            det.name or "—",
            det.rssi,
            SCAN_TYPE_LABELS.get(det.scan_type, det.scan_type),
            det.strength,
        )
        if self.tag_tree.exists(det.mac):
            self.tag_tree.item(det.mac, values=vals)
        else:
            self.tag_tree.insert("", tk.END, iid=det.mac, values=vals)

    def _on_tag_select(self, _evt=None) -> None:
        sel = self.tag_tree.selection()
        if not sel:
            return
        mac = sel[0]
        prof = self.tag_profiles.get(mac, TagProfile(mac=mac))
        self._tag_detail_vars["mac"].set(mac)
        self._tag_detail_vars["display_name"].set(prof.display_name)
        self._tag_detail_vars["scan_type"].set(prof.scan_type)
        self._tag_detail_vars["moko_password"].set(prof.moko_password)
        self._tag_detail_vars["notes"].set(prof.notes)

        det = next((d for d in self.ble.get_all() if d.mac == mac), None)
        self.txt_beacon.delete("1.0", tk.END)
        if det:
            lines = []
            if det.ibeacon:
                lines.append(det.ibeacon)
            if det.eddystone:
                lines.append(det.eddystone)
            if det.raw_mfg:
                lines.append("mfg=" + str({hex(k): v.hex() for k, v in det.raw_mfg.items()}))
            if det.uuids:
                lines.append("uuids=" + str(det.uuids))
            self.txt_beacon.insert(tk.END, "\n".join(lines) or "(no beacon payload)")

    def _save_tag_profile(self) -> None:
        mac = self._tag_detail_vars["mac"].get().strip().upper()
        if not mac:
            return
        prof = TagProfile(
            mac=mac,
            display_name=self._tag_detail_vars["display_name"].get(),
            scan_type=self._tag_detail_vars["scan_type"].get() or "UNKNOWN_BLE",
            moko_password=self._tag_detail_vars["moko_password"].get(),
            notes=self._tag_detail_vars["notes"].get(),
        )
        self.tag_profiles[mac] = prof
        save_tag_profiles(self.tag_profiles)
        self._set_status(f"Saved profile for {mac}")
        messagebox.showinfo("Saved", f"Tag profile saved for {mac}")

    # ── Forward loop ──────────────────────────────────────────────────────────

    def _start_forward_loop(self) -> None:
        self._stop_forward_loop()
        self._forward_loop()

    def _stop_forward_loop(self) -> None:
        if self._forward_job:
            self.after_cancel(self._forward_job)
            self._forward_job = None

    def _forward_loop(self) -> None:
        if not self.transport.is_connected or not self.var_forward.get():
            return
        detections = []
        for d in self.ble.get_all():
            detections.append({
                "mac_address": d.mac,
                "rssi": d.rssi,
                "signal_type": 2,
                "adv_name": d.name or "",
            })
        if detections:
            self.transport.send_detections(
                self.var_host.get().strip(),
                int(self.var_server_port.get()),
                self.var_api_key.get(),
                self.var_anchor_mac.get().strip(),
                detections,
            )
        interval = max(0.5, float(self.cfg.scan_interval_sec)) * 1000
        self._forward_job = self.after(int(interval), self._forward_loop)

    # ── Data log ──────────────────────────────────────────────────────────────

    def _log_message(self, direction: str, channel: str, message: str) -> None:
        ts = time.strftime("%H:%M:%S")
        entry = (ts, direction, channel, message)
        self._data_log.append(entry)
        if len(self._data_log) > 2000:
            self._data_log = self._data_log[-1500:]
        self.after(0, self._append_log_line, entry)

    def _append_log_line(self, entry: tuple[str, str, str, str]) -> None:
        ts, direction, channel, message = entry
        filt = self.var_log_filter.get()
        if filt != "ALL" and channel != filt:
            return
        arrow = "→" if direction == "OUT" else "←"
        line = f"[{ts}] {arrow} {channel:4} {message}\n"
        self.txt_log.insert(tk.END, line)
        self.txt_log.see(tk.END)

    def _refresh_log_view(self) -> None:
        self.txt_log.delete("1.0", tk.END)
        filt = self.var_log_filter.get()
        for entry in self._data_log:
            if filt == "ALL" or entry[2] == filt:
                self._append_log_line(entry)

    def _clear_log(self) -> None:
        self._data_log.clear()
        self.txt_log.delete("1.0", tk.END)

    def _export_log(self) -> None:
        from tkinter import filedialog

        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            for ts, direction, channel, message in self._data_log:
                f.write(f"[{ts}] {direction} {channel} {message}\n")
        messagebox.showinfo("Exported", f"Log saved to {path}")

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def _on_close(self) -> None:
        self._stop_scan()
        self._stop_forward_loop()
        self.transport.disconnect()
        self.destroy()


def main() -> None:
    app = NodeReaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
