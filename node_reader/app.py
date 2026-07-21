#!/usr/bin/env python3
"""
HOLO MQTT Broker — simple PC broker for WiFi nodes (like Mosquitto).

Runs MQTT broker on port 1883; WiFi nodes on the LAN publish tag data here.
Shows all incoming MQTT messages in a live log and parsed tag table.

  python -m node_reader
  pyinstaller node_reader/build.spec
"""
from __future__ import annotations

import sys
import time
import tkinter as tk
from tkinter import messagebox, ttk

_ROOT = __file__.replace("\\", "/").rsplit("/", 1)[0]
if _ROOT.endswith("node_reader"):
    sys.path.insert(0, _ROOT.rsplit("/", 1)[0])

from node_reader.broker_config import BrokerConfig, load_config, save_config
from node_reader.mqtt_parse import parse_mqtt_payload
from node_reader.net_ifaces import NetInterface, list_interfaces
from node_reader.pc_broker import PcMqttBroker


class MqttBrokerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("HOLO MQTT Broker — PC broker for WiFi nodes")
        self.geometry("980x640")
        self.minsize(820, 520)

        self.cfg = load_config()
        self.broker = PcMqttBroker(on_message=self._on_mqtt_message, log=self._log)
        self._ifaces: list[NetInterface] = []
        self._devices: dict[str, dict] = {}
        self._log_entries: list[tuple[str, str, str, str, str]] = []
        self._running = False

        self._build_ui()
        self._load_form()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}

        top = ttk.LabelFrame(self, text="PC MQTT broker — WiFi nodes publish here")
        top.pack(fill=tk.X, **pad)

        r0 = ttk.Frame(top)
        r0.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(r0, text="PC network:").pack(side=tk.LEFT)
        self.cmb_iface = ttk.Combobox(r0, width=48, state="readonly")
        self.cmb_iface.pack(side=tk.LEFT, padx=6)
        self.cmb_iface.bind("<<ComboboxSelected>>", self._on_iface_change)
        ttk.Button(r0, text="Refresh", command=self._refresh_interfaces).pack(side=tk.LEFT, padx=4)

        r1 = ttk.Frame(top)
        r1.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(r1, text="WiFi nodes connect to:").pack(side=tk.LEFT)
        self.lbl_connect = ttk.Label(r1, text="", font=("Consolas", 11, "bold"), foreground="#0066aa")
        self.lbl_connect.pack(side=tk.LEFT, padx=8)
        ttk.Label(r1, text="Port:").pack(side=tk.LEFT, padx=(16, 0))
        self.var_port = tk.IntVar(value=1883)
        ttk.Spinbox(r1, from_=1, to=65535, textvariable=self.var_port, width=7).pack(side=tk.LEFT, padx=4)
        ttk.Label(r1, text="(default 1883)", font=("TkDefaultFont", 8), foreground="#666").pack(side=tk.LEFT)

        r2 = ttk.Frame(top)
        r2.pack(fill=tk.X, padx=8, pady=4)
        self.btn_start = ttk.Button(r2, text="▶ Start broker", command=self._toggle_broker)
        self.btn_start.pack(side=tk.LEFT, padx=4)
        ttk.Button(r2, text="Clear log", command=self._clear_log).pack(side=tk.LEFT, padx=4)
        ttk.Button(r2, text="Clear tags", command=self._clear_tags).pack(side=tk.LEFT, padx=4)
        ttk.Button(r2, text="Save settings", command=self._save_settings).pack(side=tk.LEFT, padx=4)
        self.lbl_status = ttk.Label(r2, text="● Stopped", foreground="#c44")
        self.lbl_status.pack(side=tk.RIGHT, padx=8)
        self.lbl_stats = ttk.Label(r2, text="Messages: 0")
        self.lbl_stats.pack(side=tk.RIGHT, padx=8)

        hint = ttk.LabelFrame(self, text="WiFi node setup")
        hint.pack(fill=tk.X, **pad)
        self.lbl_hint = ttk.Label(
            hint,
            text=(
                f"On each WiFi node: MQTT broker = {ip} · port {port}\n"
                "Topic varies by firmware (e.g. rssi/data or strata/v1/bluetooth/…).\n"
                "Use server Diagnostics → Incoming traffic to see raw messages and payload format."
            ),
            justify=tk.LEFT,
            font=("TkDefaultFont", 9),
            foreground="#444",
        )
        self.lbl_hint.pack(padx=8, pady=6, anchor=tk.W)

        paned = ttk.PanedWindow(self, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, **pad)

        log_frame = ttk.LabelFrame(paned, text="MQTT messages (live)")
        paned.add(log_frame, weight=3)
        cols_log = ("time", "client", "topic", "payload")
        self.msg_tree = ttk.Treeview(log_frame, columns=cols_log, show="headings", height=12)
        for c, w in zip(cols_log, (70, 100, 140, 520)):
            self.msg_tree.heading(c, text=c.upper())
            self.msg_tree.column(c, width=w)
        self.msg_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        tag_frame = ttk.LabelFrame(paned, text="Parsed tags (from rssi/data, ble/rssi, etc.)")
        paned.add(tag_frame, weight=2)
        cols_tag = ("mac", "rssi", "topic", "age")
        self.tag_tree = ttk.Treeview(tag_frame, columns=cols_tag, show="headings", height=6)
        for c, w in zip(cols_tag, (160, 60, 160, 60)):
            self.tag_tree.heading(c, text=c.upper())
            self.tag_tree.column(c, width=w)
        self.tag_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.statusbar = ttk.Label(self, text="Ready — Start broker, then configure WiFi nodes", relief=tk.SUNKEN, anchor=tk.W)
        self.statusbar.pack(fill=tk.X, side=tk.BOTTOM, padx=8, pady=(0, 6))

    def _refresh_interfaces(self, select_key: str | None = None) -> None:
        self._ifaces = list_interfaces()
        labels = [i.label for i in self._ifaces]
        self.cmb_iface["values"] = labels
        if not labels:
            self.cmb_iface.set("(no interfaces)")
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

    def _pc_ip(self) -> str:
        iface = self._selected_iface()
        if iface:
            return iface.ip
        return self.cfg.network_bind_ip or "YOUR_PC_IP"

    def _on_iface_change(self, _evt=None) -> None:
        ip = self._pc_ip()
        port = int(self.var_port.get())
        self.lbl_connect.configure(text=f"mqtt://{ip}:{port}")
        self.lbl_hint.configure(
            text=(
                f"On each WiFi node: MQTT broker = {ip} · port {port}\n"
                "Topic varies by firmware — inspect raw traffic in HOLO server Diagnostics.\n"
                f"Allow inbound TCP {port} in Windows Firewall."
            )
        )

    def _load_form(self) -> None:
        self.var_port.set(self.cfg.broker_port)
        self._refresh_interfaces(select_key=self.cfg.network_interface_key)
        if self.cfg.auto_start:
            self.after(500, self._toggle_broker)

    def _save_settings(self) -> None:
        iface = self._selected_iface()
        if iface:
            self.cfg.network_interface_key = iface.key
            self.cfg.network_bind_ip = iface.ip
        self.cfg.broker_port = int(self.var_port.get())
        save_config(self.cfg)
        self._set_status("Settings saved")

    def _toggle_broker(self) -> None:
        if self._running:
            self.broker.stop()
            self._running = False
            self.btn_start.configure(text="▶ Start broker")
            self.lbl_status.configure(text="● Stopped", foreground="#c44")
            self._set_status("Broker stopped")
            return
        self._save_settings()
        self.broker.port = int(self.var_port.get())
        ok, msg = self.broker.start()
        if not ok:
            messagebox.showerror(
                "Broker failed",
                f"{msg}\n\n"
                "Try:\n"
                "• Run as Administrator\n"
                "• Close other MQTT/Mosquitto on port 1883\n"
                "• Windows Firewall → allow inbound TCP 1883",
            )
            return
        self._running = True
        self.btn_start.configure(text="■ Stop broker")
        self.lbl_status.configure(text=f"● Running :{self.var_port.get()}", foreground="#2a8")
        self._set_status(msg)

    def _on_mqtt_message(self, client_id: str, topic: str, payload: str) -> None:
        ts = time.strftime("%H:%M:%S")
        entry = (ts, client_id, topic, payload)
        self._log_entries.append(entry)
        if len(self._log_entries) > 5000:
            self._log_entries = self._log_entries[-3000:]
        self.after(0, self._append_message, entry)
        devices = parse_mqtt_payload(payload, topic)
        if devices:
            self.after(0, lambda: self._merge_tags(devices, topic))

    def _append_message(self, entry: tuple[str, str, str, str]) -> None:
        ts, client_id, topic, payload = entry
        preview = payload.replace("\n", " ")[:300]
        self.msg_tree.insert("", 0, values=(ts, client_id, topic, preview))
        children = self.msg_tree.get_children()
        if len(children) > 2000:
            for iid in children[2000:]:
                self.msg_tree.delete(iid)
        self.lbl_stats.configure(text=f"Messages: {self.broker.message_count}")

    def _merge_tags(self, devices, topic: str) -> None:
        now = time.time()
        for d in devices:
            mac = d.mac
            if not mac:
                continue
            self._devices[mac] = {
                "mac": mac,
                "rssi": d.rssi,
                "topic": topic,
                "last_seen": now,
            }
        self._refresh_tags()

    def _refresh_tags(self) -> None:
        now = time.time()
        seen = set()
        for mac, d in self._devices.items():
            seen.add(mac)
            age = int(now - d["last_seen"])
            vals = (mac, d.get("rssi", -999), d.get("topic", ""), f"{age}s")
            if self.tag_tree.exists(mac):
                self.tag_tree.item(mac, values=vals)
            else:
                self.tag_tree.insert("", tk.END, iid=mac, values=vals)
        for iid in self.tag_tree.get_children():
            if iid not in seen:
                self.tag_tree.delete(iid)

    def _clear_log(self) -> None:
        self._log_entries.clear()
        for i in self.msg_tree.get_children():
            self.msg_tree.delete(i)

    def _clear_tags(self) -> None:
        self._devices.clear()
        for i in self.tag_tree.get_children():
            self.tag_tree.delete(i)

    def _log(self, direction: str, channel: str, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.after(0, self._append_message, (ts, direction, channel, msg))

    def _set_status(self, text: str) -> None:
        self.statusbar.configure(text=text)

    def _on_close(self) -> None:
        if self._running:
            self.broker.stop()
        self.destroy()


def main() -> None:
    MqttBrokerApp().mainloop()


if __name__ == "__main__":
    main()
