#!/usr/bin/env python3
"""
HOLO-RTLS Node Reader — Windows app for BlueApro 6/6E WiFi nodes (vendor firmware).

Connects to node via HTTP (user-selected port), polls or receives tag data,
displays raw traffic, optional uplink to central HOLO-RTLS.

  python -m node_reader
  pyinstaller node_reader/build.spec
"""
from __future__ import annotations

import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

_ROOT = __file__.replace("\\", "/").rsplit("/", 1)[0]
if _ROOT.endswith("node_reader"):
    sys.path.insert(0, _ROOT.rsplit("/", 1)[0])

from node_reader.blueapro_client import BlueAproClient, NodeDevice
from node_reader.config_store import AppConfig, TagProfile, load_config, load_tag_profiles, save_config, save_tag_profiles
from node_reader.discovery import scan_network
from node_reader.ingest_server import IngestServer
from node_reader.net_ifaces import NetInterface, find_interface, list_interfaces
from node_reader.tag_classifier import SCAN_TYPE_LABELS
from node_reader.transport import ServerTransport


class NodeReaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("HOLO-RTLS Node Reader — BlueApro 6/6E")
        self.geometry("1020x680")
        self.minsize(900, 560)

        self.cfg = load_config()
        self.tag_profiles = load_tag_profiles()
        self.transport = ServerTransport(log=self._log)
        self.ingest = IngestServer(
            host=self.cfg.listen_host,
            port=self.cfg.listen_port,
            ingest_path=self.cfg.listen_path,
            on_devices=self._on_push_devices,
            log=self._log,
        )

        self._client: BlueAproClient | None = None
        self._connected = False
        self._polling = False
        self._poll_job = None
        self._devices: dict[str, dict] = {}
        self._data_log: list[tuple[str, str, str, str]] = []
        self._ifaces: list = []
        self._poll_err_count = 0
        self._poll_warn_shown = False

        self._build_ui()
        self._load_form()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.tab_node = ttk.Frame(nb)
        self.tab_tags = ttk.Frame(nb)
        self.tab_log = ttk.Frame(nb)
        self.tab_adv = ttk.Frame(nb)
        nb.add(self.tab_node, text="  BlueApro Node  ")
        nb.add(self.tab_tags, text="  Tags  ")
        nb.add(self.tab_log, text="  Data log  ")
        nb.add(self.tab_adv, text="  Advanced  ")

        self._build_node_tab()
        self._build_tags_tab()
        self._build_log_tab()
        self._build_adv_tab()

        self.status = ttk.Label(self, text="Ready — configure BlueApro node and Connect", relief=tk.SUNKEN, anchor=tk.W)
        self.status.pack(fill=tk.X, side=tk.BOTTOM, padx=8, pady=(0, 6))

    def _build_node_tab(self) -> None:
        f = self.tab_node
        pad = {"padx": 8, "pady": 4}

        info = ttk.LabelFrame(f, text="Device profile")
        info.pack(fill=tk.X, **pad)
        r0 = ttk.Frame(info)
        r0.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(r0, text="Model:").pack(side=tk.LEFT)
        self.var_model = tk.StringVar(value=BlueAproClient.MODEL)
        ttk.Label(r0, textvariable=self.var_model, font=("TkDefaultFont", 9, "bold")).pack(side=tk.LEFT, padx=6)
        ttk.Label(r0, text="S/N:").pack(side=tk.LEFT, padx=(16, 0))
        self.var_serial = tk.StringVar()
        ttk.Entry(r0, textvariable=self.var_serial, width=22).pack(side=tk.LEFT, padx=6)

        conn = ttk.LabelFrame(f, text="Connect to BlueApro node (HTTP)")
        conn.pack(fill=tk.X, **pad)

        net = ttk.Frame(conn)
        net.pack(fill=tk.X, padx=8, pady=(6, 2))
        ttk.Label(net, text="PC network:").pack(side=tk.LEFT)
        self.cmb_iface = ttk.Combobox(net, width=52, state="readonly")
        self.cmb_iface.pack(side=tk.LEFT, padx=6)
        self.cmb_iface.bind("<<ComboboxSelected>>", self._on_iface_change)
        ttk.Button(net, text="Refresh", command=self._refresh_interfaces).pack(side=tk.LEFT, padx=4)
        self.lbl_iface_hint = ttk.Label(
            net,
            text="",
            font=("TkDefaultFont", 8),
            foreground="#666",
        )
        self.lbl_iface_hint.pack(side=tk.LEFT, padx=8)

        r1 = ttk.Frame(conn)
        r1.pack(fill=tk.X, padx=8, pady=6)
        ttk.Button(r1, text="Scan WiFi nodes", command=self._scan_nodes).pack(side=tk.LEFT)
        ttk.Label(r1, text="Node IP:").pack(side=tk.LEFT, padx=(12, 0))
        self.var_host = tk.StringVar()
        ttk.Entry(r1, textvariable=self.var_host, width=18).pack(side=tk.LEFT, padx=4)
        ttk.Label(r1, text="Port:").pack(side=tk.LEFT, padx=(8, 0))
        self.var_port = tk.IntVar(value=80)
        ttk.Spinbox(r1, from_=1, to=65535, textvariable=self.var_port, width=7).pack(side=tk.LEFT, padx=4)
        self.var_https = tk.BooleanVar(value=False)
        ttk.Checkbutton(r1, text="HTTPS", variable=self.var_https).pack(side=tk.LEFT, padx=6)

        r2 = ttk.Frame(conn)
        r2.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(r2, text="HTTP mode:").pack(side=tk.LEFT)
        self.var_http_mode = tk.StringVar(value="pull")
        ttk.Radiobutton(r2, text="Pull (PC → node GET)", variable=self.var_http_mode, value="pull").pack(side=tk.LEFT, padx=6)
        ttk.Radiobutton(r2, text="Push (node POST → PC)", variable=self.var_http_mode, value="push").pack(side=tk.LEFT, padx=6)

        r3 = ttk.Frame(conn)
        r3.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(r3, text="Node user:").pack(side=tk.LEFT)
        self.var_user = tk.StringVar(value="admin")
        ttk.Entry(r3, textvariable=self.var_user, width=12).pack(side=tk.LEFT, padx=4)
        ttk.Label(r3, text="Node password:").pack(side=tk.LEFT, padx=(8, 0))
        self.var_node_pass = tk.StringVar()
        ttk.Entry(r3, textvariable=self.var_node_pass, width=16, show="*").pack(side=tk.LEFT, padx=4)
        ttk.Label(r3, text="(BlueApro web UI password)", font=("TkDefaultFont", 8), foreground="#666").pack(side=tk.LEFT, padx=6)

        pick = ttk.LabelFrame(f, text="Discovered nodes — select to fill IP + port")
        pick.pack(fill=tk.BOTH, expand=True, **pad)
        cols = ("ip", "port", "ports", "label")
        self.node_tree = ttk.Treeview(pick, columns=cols, show="headings", height=5)
        for c, w in zip(cols, (130, 60, 120, 160)):
            self.node_tree.heading(c, text=c.upper())
            self.node_tree.column(c, width=w)
        self.node_tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        self.node_tree.bind("<<TreeviewSelect>>", self._on_node_pick)

        act = ttk.Frame(f)
        act.pack(fill=tk.X, **pad)
        ttk.Button(act, text="Test node", command=self._test_node).pack(side=tk.LEFT, padx=4)
        ttk.Button(act, text="Probe API paths", command=self._probe_node).pack(side=tk.LEFT, padx=4)
        self.btn_connect = ttk.Button(act, text="Connect", command=self._toggle_connect)
        self.btn_connect.pack(side=tk.LEFT, padx=4)
        ttk.Button(act, text="Open local dashboard", command=self._open_dashboard).pack(side=tk.LEFT, padx=4)
        ttk.Button(act, text="Save settings", command=self._save_settings).pack(side=tk.LEFT, padx=4)
        self.lbl_conn = ttk.Label(act, text="● Disconnected", foreground="#c44")
        self.lbl_conn.pack(side=tk.RIGHT, padx=8)

        push = ttk.LabelFrame(f, text="Push mode — configure BlueApro transport URI to this PC")
        push.pack(fill=tk.X, **pad)
        self.lbl_push_uri = ttk.Label(push, text="", font=("Consolas", 9))
        self.lbl_push_uri.pack(padx=8, pady=6, anchor=tk.W)
        ttk.Label(
            push,
            text="In BlueApro web UI → Transport → HTTP → set URI to the address above (Basic Auth optional).",
            font=("TkDefaultFont", 8),
            foreground="#666",
        ).pack(padx=8, pady=(0, 2), anchor=tk.W)

        flow = ttk.LabelFrame(f, text="How this screen connects to your BlueApro (from your setup)")
        flow.pack(fill=tk.X, **pad)
        ttk.Label(
            flow,
            text=(
                "1) Select PC network (Wi-Fi or Ethernet) — must be same LAN as the node.\n"
                "2) Scan WiFi nodes → picks hosts on that subnet (e.g. 10.7.15.x).\n"
                "3) Click a row → fills Node IP + Port (80 or 8080).\n"
                "4) Pull: Test node → Connect → Tags → Start receiving (PC GETs node).\n"
                "5) Push: set BlueApro transport URI to this PC IP below → Connect → Start receiving."
            ),
            justify=tk.LEFT,
            font=("TkDefaultFont", 8),
            foreground="#444",
        ).pack(padx=8, pady=6, anchor=tk.W)

    def _refresh_interfaces(self, select_key: str | None = None) -> None:
        self._ifaces = list_interfaces()
        labels = [i.label for i in self._ifaces]
        self.cmb_iface["values"] = labels
        if not labels:
            self.cmb_iface.set("(no interfaces)")
            self.lbl_iface_hint.configure(text="")
            return
        key = select_key or self.cfg.network_interface_key
        idx = 0
        for i, iface in enumerate(self._ifaces):
            if iface.key == key or iface.ip == self.cfg.network_bind_ip:
                idx = i
                break
        self.cmb_iface.current(idx)
        self._on_iface_change()

    def _selected_iface(self) -> NetInterface | None:
        if not self._ifaces:
            return None
        idx = self.cmb_iface.current()
        if idx < 0 or idx >= len(self._ifaces):
            return self._ifaces[0]
        return self._ifaces[idx]

    def _on_iface_change(self, _evt=None) -> None:
        iface = self._selected_iface()
        if not iface:
            return
        self.cfg.network_interface_key = iface.key
        self.cfg.network_bind_ip = iface.ip
        self.lbl_iface_hint.configure(
            text=f"Scan subnet {iface.subnet_prefix}.x · Push URI uses {iface.ip}"
        )
        self._update_push_uri()
        if self.ingest.running:
            self.ingest.stop()
            self.ingest.host = iface.ip
            self.ingest.start()

    def _bind_ip(self) -> str | None:
        iface = self._selected_iface()
        return iface.ip if iface else (self.cfg.network_bind_ip or None)

    def _subnet_prefix(self) -> str | None:
        iface = self._selected_iface()
        return iface.subnet_prefix if iface else None

    def _start_ingest(self) -> tuple[bool, str]:
        self.ingest.port = int(self.var_listen_port.get())
        bind = self._bind_ip()
        self.ingest.host = bind or "0.0.0.0"
        if self.ingest.running:
            return True, f"Listening on {bind or '0.0.0.0'}:{self.ingest.port}"
        return self.ingest.start()

    def _build_tags_tab(self) -> None:
        f = self.tab_tags
        pad = {"padx": 8, "pady": 4}
        bar = ttk.Frame(f)
        bar.pack(fill=tk.X, **pad)
        self.btn_poll = ttk.Button(bar, text="▶ Start receiving tags", command=self._toggle_polling)
        self.btn_poll.pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Refresh now", command=self._poll_once).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Clear", command=self._clear_tags).pack(side=tk.LEFT, padx=4)
        self.var_uplink = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Forward to central HOLO-RTLS", variable=self.var_uplink).pack(side=tk.LEFT, padx=12)
        self.lbl_poll = ttk.Label(bar, text="Stopped")
        self.lbl_poll.pack(side=tk.RIGHT, padx=8)

        paned = ttk.PanedWindow(f, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, **pad)
        left = ttk.Frame(paned)
        paned.add(left, weight=3)
        cols = ("mac", "name", "rssi", "type", "source", "age")
        self.tag_tree = ttk.Treeview(left, columns=cols, show="headings")
        for c, w in zip(cols, (140, 110, 55, 90, 70, 60)):
            self.tag_tree.heading(c, text=c.upper())
            self.tag_tree.column(c, width=w)
        self.tag_tree.pack(fill=tk.BOTH, expand=True)
        self.tag_tree.bind("<<TreeviewSelect>>", self._on_tag_pick)

        right = ttk.LabelFrame(paned, text="Tag settings")
        paned.add(right, weight=2)
        self._tag_vars = {}
        row = 0
        for key, label, ro in [("mac", "MAC", True), ("display_name", "Display name", False), ("scan_type", "Scan type", False),
                                ("moko_password", "MOKO / tag password", False), ("notes", "Notes", False)]:
            ttk.Label(right, text=label + ":").grid(row=row, column=0, sticky=tk.W, padx=8, pady=3)
            var = tk.StringVar()
            self._tag_vars[key] = var
            kw = {"width": 32, "state": "readonly" if ro else "normal"}
            if key == "moko_password":
                kw["show"] = "*"
            ttk.Entry(right, textvariable=var, **kw).grid(row=row, column=1, sticky=tk.EW, padx=8, pady=3)
            row += 1
        self.cmb_type = ttk.Combobox(right, textvariable=self._tag_vars["scan_type"], values=list(SCAN_TYPE_LABELS.keys()), state="readonly", width=30)
        self.cmb_type.grid(row=2, column=1, sticky=tk.EW, padx=8, pady=3)
        ttk.Label(right, text="Raw payload:").grid(row=row, column=0, sticky=tk.NW, padx=8, pady=4)
        self.txt_raw = tk.Text(right, height=8, width=42, font=("Consolas", 9))
        self.txt_raw.grid(row=row, column=1, sticky=tk.NSEW, padx=8, pady=4)
        right.rowconfigure(row, weight=1)
        right.columnconfigure(1, weight=1)
        row += 1
        ttk.Button(right, text="Save tag profile", command=self._save_tag).grid(row=row, column=1, sticky=tk.E, padx=8, pady=8)

    def _build_log_tab(self) -> None:
        f = self.tab_log
        pad = {"padx": 8, "pady": 4}
        bar = ttk.Frame(f)
        bar.pack(fill=tk.X, **pad)
        self.var_filt = tk.StringVar(value="ALL")
        for v in ("ALL", "NODE", "LOCAL", "UPLINK"):
            ttk.Radiobutton(bar, text=v, variable=self.var_filt, value=v, command=self._refresh_log).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Clear", command=self._clear_log).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bar, text="Export", command=self._export_log).pack(side=tk.RIGHT, padx=4)
        self.txt_log = tk.Text(f, font=("Consolas", 9))
        self.txt_log.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

    def _build_adv_tab(self) -> None:
        f = self.tab_adv
        pad = {"padx": 8, "pady": 4}
        api = ttk.LabelFrame(f, text="Node API paths (vendor firmware)")
        api.pack(fill=tk.X, **pad)
        self.var_dev_path = tk.StringVar(value="/api/ble/devices")
        self.var_health_path = tk.StringVar(value="/api/system")
        self.var_listen_port = tk.IntVar(value=8765)
        self.var_poll_sec = tk.DoubleVar(value=2.0)
        fields = [
            ("Devices GET path:", self.var_dev_path),
            ("Health GET path:", self.var_health_path),
            ("PC listen port (push):", self.var_listen_port),
            ("Poll interval (sec):", self.var_poll_sec),
        ]
        for i, (lbl, var) in enumerate(fields):
            ttk.Label(api, text=lbl).grid(row=i, column=0, sticky=tk.W, padx=8, pady=4)
            ttk.Entry(api, textvariable=var, width=40).grid(row=i, column=1, sticky=tk.W, padx=8, pady=4)

        upl = ttk.LabelFrame(f, text="Optional uplink — central HOLO-RTLS server")
        upl.pack(fill=tk.X, **pad)
        self.var_up_host = tk.StringVar(value="127.0.0.1")
        self.var_up_port = tk.IntVar(value=5000)
        self.var_up_key = tk.StringVar(value="scanner-dev-key")
        self.var_up_mac = tk.StringVar()
        for i, (lbl, var) in enumerate([
            ("Server host:", self.var_up_host),
            ("Server HTTP port:", self.var_up_port),
            ("Scanner API key:", self.var_up_key),
            ("Anchor MAC (this node):", self.var_up_mac),
        ]):
            ttk.Label(upl, text=lbl).grid(row=i, column=0, sticky=tk.W, padx=8, pady=4)
            ttk.Entry(upl, textvariable=var, width=40, show="*" if "key" in lbl.lower() else "").grid(row=i, column=1, padx=8, pady=4)

    # ── Config ────────────────────────────────────────────────────────────────

    def _load_form(self) -> None:
        c = self.cfg
        self.var_host.set(c.node_host)
        self.var_port.set(c.node_port)
        self.var_https.set(c.node_use_https)
        self.var_user.set(c.node_username)
        self.var_node_pass.set(c.node_password)
        self.var_serial.set(c.node_serial or "261FBLUEAO004")
        self.var_http_mode.set(c.http_mode)
        self.var_dev_path.set(c.devices_path)
        self.var_health_path.set(c.health_path)
        self.var_listen_port.set(c.listen_port)
        self.var_poll_sec.set(c.poll_interval_sec)
        self.var_uplink.set(c.uplink_enabled)
        self.var_up_host.set(c.uplink_host)
        self.var_up_port.set(c.uplink_port)
        self.var_up_key.set(c.uplink_api_key)
        self.var_up_mac.set(c.uplink_anchor_mac)
        self._refresh_interfaces(select_key=c.network_interface_key)
        self._update_push_uri()

    def _save_settings(self) -> None:
        iface = self._selected_iface()
        if iface:
            self.cfg.network_interface_key = iface.key
            self.cfg.network_bind_ip = iface.ip
        self.cfg.node_host = self.var_host.get().strip()
        self.cfg.node_port = int(self.var_port.get())
        self.cfg.node_use_https = bool(self.var_https.get())
        self.cfg.node_username = self.var_user.get().strip()
        self.cfg.node_password = self.var_node_pass.get()
        self.cfg.node_serial = self.var_serial.get().strip()
        self.cfg.http_mode = self.var_http_mode.get()
        self.cfg.devices_path = self.var_dev_path.get().strip()
        self.cfg.health_path = self.var_health_path.get().strip()
        self.cfg.listen_port = int(self.var_listen_port.get())
        self.cfg.poll_interval_sec = float(self.var_poll_sec.get())
        self.cfg.uplink_enabled = bool(self.var_uplink.get())
        self.cfg.uplink_host = self.var_up_host.get().strip()
        self.cfg.uplink_port = int(self.var_up_port.get())
        self.cfg.uplink_api_key = self.var_up_key.get()
        self.cfg.uplink_anchor_mac = self.var_up_mac.get().strip().upper()
        save_config(self.cfg)
        self._update_push_uri()
        self._set_status("Settings saved")

    def _client_instance(self) -> BlueAproClient:
        return BlueAproClient(
            host=self.var_host.get().strip(),
            port=int(self.var_port.get()),
            use_https=bool(self.var_https.get()),
            username=self.var_user.get().strip(),
            password=self.var_node_pass.get(),
            devices_path=self.var_dev_path.get().strip(),
            health_path=self.var_health_path.get().strip(),
            source_ip=self._bind_ip(),
        )

    def _update_push_uri(self) -> None:
        port = int(self.var_listen_port.get())
        path = self.cfg.listen_path
        pc_ip = self._bind_ip() or "YOUR_PC_IP"
        self.lbl_push_uri.configure(text=f"http://{pc_ip}:{port}{path}")

    # ── Node actions ──────────────────────────────────────────────────────────

    def _scan_nodes(self) -> None:
        iface = self._selected_iface()
        subnet = self._subnet_prefix()
        bind = self._bind_ip()
        hint = f" on {iface.name} ({subnet}.x)" if iface else ""
        self._set_status(f"Scanning network{hint}…")
        ports = self.cfg.discovery_ports

        def work():
            nodes = scan_network(ports=ports, subnet_prefix=subnet, bind_ip=bind)
            self.after(0, lambda: self._scan_done(nodes))

        threading.Thread(target=work, daemon=True).start()

    def _scan_done(self, nodes) -> None:
        for i in self.node_tree.get_children():
            self.node_tree.delete(i)
        for n in nodes:
            self.node_tree.insert("", tk.END, values=(n.ip, n.port, ",".join(map(str, n.open_ports)), n.label))
        self._set_status(f"Found {len(nodes)} host(s)")
        if not nodes:
            messagebox.showinfo("Scan", "No nodes found. Try direct IP 192.168.4.1 (BlueApro AP mode) or check LAN.")

    def _on_node_pick(self, _evt=None) -> None:
        sel = self.node_tree.selection()
        if not sel:
            return
        vals = self.node_tree.item(sel[0], "values")
        if vals:
            self.var_host.set(vals[0])
            self.var_port.set(int(vals[1]))

    def _probe_node(self) -> None:
        client = self._client_instance()
        self._set_status("Probing node HTTP paths…")

        def work():
            rows = client.probe_endpoints()
            self.after(0, lambda: self._probe_done(rows))

        threading.Thread(target=work, daemon=True).start()

    def _probe_done(self, rows: list[tuple[str, int, str]]) -> None:
        lines = ["Path probe results:", ""]
        for path, code, hint in rows:
            lines.append(f"  {path:30} → {code if code >= 0 else 'ERR'}  ({hint})")
        lines.append("")
        lines.append("BlueApro tags need a 200 on a BLE devices path, OR use Push mode.")
        text = "\n".join(lines)
        self._log("OUT", "NODE", "Probe API paths")
        for line in lines[2:-2]:
            if line.strip():
                self._log("IN", "NODE", line.strip())
        messagebox.showinfo("API probe", text)
        self._set_status("Probe complete — see Data log")

    def _test_node(self) -> None:
        if self.var_http_mode.get() == "push":
            ok, msg = self._start_ingest()
            if ok:
                messagebox.showinfo("Push mode", f"Local listener OK.\nConfigure BlueApro URI:\n{self.lbl_push_uri.cget('text')}")
            else:
                messagebox.showerror("Push mode", msg)
            return
        res = self._client_instance().test_connection()
        if res.ok:
            msg = res.message
            if res.detail:
                msg += f"\n\n{res.detail}"
            messagebox.showinfo("Test OK", msg)
        else:
            messagebox.showerror("Test failed", f"{res.message}\n\n{res.detail}")
        self._log("OUT", "NODE", f"TEST → {res.message}")

    def _toggle_connect(self) -> None:
        if self._connected:
            self._disconnect()
            return
        self._save_settings()
        mode = self.var_http_mode.get()
        if mode == "push":
            ok, msg = self._start_ingest()
            if not ok:
                messagebox.showerror("Connect failed", msg)
                return
            self._connected = True
            self.btn_connect.configure(text="Disconnect")
            self.lbl_conn.configure(text="● Listening (push mode)", foreground="#2a8")
            self._set_status(msg)
            self._log("OUT", "LOCAL", msg)
            return

        res = self._client_instance().test_connection()
        if not res.ok:
            messagebox.showerror("Connect failed", f"{res.message}\n\n{res.detail}")
            return
        if res.detail and "Push mode" in res.detail:
            if messagebox.askyesno(
                "Use Push mode?",
                f"{res.message}\n\n{res.detail}\n\nSwitch to Push mode now?",
            ):
                self.var_http_mode.set("push")
                ok, msg = self._start_ingest()
                if not ok:
                    messagebox.showerror("Connect failed", msg)
                    return
                self._connected = True
                self.btn_connect.configure(text="Disconnect")
                self.lbl_conn.configure(text="● Listening (push mode)", foreground="#2a8")
                self._set_status(msg)
                self._log("OUT", "LOCAL", msg)
                return

        self._client = self._client_instance()
        self._connected = True
        self._poll_err_count = 0
        self._poll_warn_shown = False
        self.btn_connect.configure(text="Disconnect")
        self.lbl_conn.configure(text=f"● Connected {self.var_host.get()}:{self.var_port.get()}", foreground="#2a8")
        self._set_status(res.message)
        self._log("OUT", "NODE", f"CONNECT {self._client.base_url}")

        if not self.ingest.running:
            self._start_ingest()

    def _disconnect(self) -> None:
        self._stop_polling()
        self._connected = False
        self._client = None
        self.btn_connect.configure(text="Connect")
        self.lbl_conn.configure(text="● Disconnected", foreground="#c44")
        self._set_status("Disconnected")

    # ── Tags ──────────────────────────────────────────────────────────────────

    def _toggle_polling(self) -> None:
        if self._polling:
            self._stop_polling()
        else:
            if not self._connected:
                messagebox.showwarning("Not connected", "Connect to BlueApro node first.")
                return
            self._polling = True
            self.btn_poll.configure(text="■ Stop receiving tags")
            self.lbl_poll.configure(text="Receiving…")
            if self.var_http_mode.get() == "pull" and self._client:
                self._client.start_scan()
            self._poll_loop()

    def _stop_polling(self) -> None:
        self._polling = False
        if self._poll_job:
            self.after_cancel(self._poll_job)
            self._poll_job = None
        self.btn_poll.configure(text="▶ Start receiving tags")
        self.lbl_poll.configure(text="Stopped")
        if self._client:
            self._client.stop_scan()

    def _poll_loop(self) -> None:
        if not self._polling:
            return
        if self.var_http_mode.get() == "pull":
            self._poll_once()
        interval = max(0.5, float(self.var_poll_sec.get())) * 1000
        self._poll_job = self.after(int(interval), self._poll_loop)

    def _poll_once(self) -> None:
        if self.var_http_mode.get() == "push":
            self._merge_devices(self.ingest.state.devices.values(), "node-push")
            return
        if not self._client:
            return

        def work():
            devices, err = self._client.fetch_devices()
            self.after(0, lambda: self._poll_result(devices, err))

        threading.Thread(target=work, daemon=True).start()

    def _poll_result(self, devices: list[NodeDevice], err: str) -> None:
        if err:
            self._poll_err_count += 1
            if self._poll_err_count <= 3 or self._poll_err_count % 15 == 0:
                self._log("IN", "NODE", f"Poll error: {err}")
            self._set_status(err[:120])
            if not self._poll_warn_shown and self._poll_err_count >= 3:
                self._poll_warn_shown = True
                self.after(0, lambda: messagebox.showwarning(
                    "No tags from Pull mode",
                    f"{err}\n\n"
                    "Your BlueApro likely does not support Pull (GET /api/tags).\n"
                    "Switch to Push mode and set BlueApro transport URI to:\n"
                    f"  {self.lbl_push_uri.cget('text')}",
                ))
            return
        self._poll_err_count = 0
        self._log("IN", "NODE", f"GET devices → {len(devices)} tag(s)")
        self._merge_devices(devices, "node")
        if self.var_uplink.get() and devices:
            self._uplink(devices)

    def _on_push_devices(self, devices: list[NodeDevice]) -> None:
        self.after(0, lambda: self._merge_devices(devices, "node-push"))
        self._log("IN", "NODE", f"POST push → {len(devices)} tag(s)")
        if self.var_uplink.get() and devices:
            self._uplink(devices)

    def _merge_devices(self, devices, source: str) -> None:
        now = time.time()
        for d in devices:
            mac = d.mac if hasattr(d, "mac") else d.get("mac", "")
            if not mac:
                continue
            name = getattr(d, "name", None) or d.get("name", "")
            rssi = getattr(d, "rssi", None) if hasattr(d, "rssi") else d.get("rssi", -999)
            st = getattr(d, "scan_type", None) or d.get("scan_type", "UNKNOWN_BLE")
            raw = getattr(d, "raw", None) or d
            self._devices[mac] = {
                "mac": mac, "name": name, "rssi": rssi, "scan_type": st,
                "source": source, "last_seen": now, "raw": raw,
            }
        self._refresh_tag_tree()

    def _refresh_tag_tree(self) -> None:
        now = time.time()
        for mac, d in self._devices.items():
            age = int(now - d["last_seen"])
            vals = (
                mac,
                d.get("name") or "—",
                d.get("rssi", -999),
                SCAN_TYPE_LABELS.get(d.get("scan_type", ""), d.get("scan_type", "")),
                d.get("source", ""),
                f"{age}s",
            )
            if self.tag_tree.exists(mac):
                self.tag_tree.item(mac, values=vals)
            else:
                self.tag_tree.insert("", tk.END, iid=mac, values=vals)

    def _clear_tags(self) -> None:
        self._devices.clear()
        for i in self.tag_tree.get_children():
            self.tag_tree.delete(i)

    def _on_tag_pick(self, _evt=None) -> None:
        sel = self.tag_tree.selection()
        if not sel:
            return
        mac = sel[0]
        prof = self.tag_profiles.get(mac, TagProfile(mac=mac))
        self._tag_vars["mac"].set(mac)
        self._tag_vars["display_name"].set(prof.display_name)
        self._tag_vars["scan_type"].set(prof.scan_type)
        self._tag_vars["moko_password"].set(prof.moko_password)
        self._tag_vars["notes"].set(prof.notes)
        self.txt_raw.delete("1.0", tk.END)
        rec = self._devices.get(mac, {})
        raw = rec.get("raw")
        if raw:
            import json
            try:
                self.txt_raw.insert(tk.END, json.dumps(raw, indent=2)[:4000])
            except Exception:
                self.txt_raw.insert(tk.END, str(raw)[:4000])

    def _save_tag(self) -> None:
        mac = self._tag_vars["mac"].get().strip().upper()
        if not mac:
            return
        self.tag_profiles[mac] = TagProfile(
            mac=mac,
            display_name=self._tag_vars["display_name"].get(),
            scan_type=self._tag_vars["scan_type"].get() or "UNKNOWN_BLE",
            moko_password=self._tag_vars["moko_password"].get(),
            notes=self._tag_vars["notes"].get(),
        )
        save_tag_profiles(self.tag_profiles)
        messagebox.showinfo("Saved", f"Tag profile saved for {mac}")

    def _uplink(self, devices: list) -> None:
        detections = []
        for d in devices:
            mac = d.mac if hasattr(d, "mac") else d.get("mac")
            rssi = d.rssi if hasattr(d, "rssi") else d.get("rssi", -999)
            name = getattr(d, "name", "") if hasattr(d, "name") else d.get("name", "")
            detections.append({"mac_address": mac, "rssi": rssi, "signal_type": 2, "adv_name": name or ""})
        anchor = self.var_up_mac.get().strip() or self.var_host.get()
        res = self.transport.send_detections(
            self.var_up_host.get(), int(self.var_up_port.get()),
            self.var_up_key.get(), anchor, detections,
        )
        ch = "UPLINK"
        self._log("OUT" if res.ok else "IN", ch, f"Forward → {res.message}")

    # ── Log ───────────────────────────────────────────────────────────────────

    def _log(self, direction: str, channel: str, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        entry = (ts, direction, channel, msg)
        self._data_log.append(entry)
        if len(self._data_log) > 3000:
            self._data_log = self._data_log[-2000:]
        self.after(0, self._append_log, entry)

    def _append_log(self, entry) -> None:
        ts, direction, channel, msg = entry
        filt = self.var_filt.get()
        if filt != "ALL" and channel != filt:
            return
        arrow = "→" if direction == "OUT" else "←"
        self.txt_log.insert(tk.END, f"[{ts}] {arrow} {channel:6} {msg}\n")
        self.txt_log.see(tk.END)

    def _refresh_log(self) -> None:
        self.txt_log.delete("1.0", tk.END)
        for e in self._data_log:
            self._append_log(e)

    def _clear_log(self) -> None:
        self._data_log.clear()
        self.txt_log.delete("1.0", tk.END)

    def _export_log(self) -> None:
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(defaultextension=".txt")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            for ts, d, c, m in self._data_log:
                f.write(f"[{ts}] {d} {c} {m}\n")

    def _open_dashboard(self) -> None:
        port = int(self.var_listen_port.get())
        if not self.ingest.running:
            self._start_ingest()
        host = self._bind_ip() or "127.0.0.1"
        webbrowser.open(f"http://{host}:{port}/")

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def _on_close(self) -> None:
        self._stop_polling()
        self.ingest.stop()
        self.transport.disconnect()
        self.destroy()


def main() -> None:
    NodeReaderApp().mainloop()


if __name__ == "__main__":
    main()
