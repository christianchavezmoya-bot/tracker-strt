"""UDP and TCP listeners for BlueApro Raw UDP / Raw TCP transport."""
from __future__ import annotations

import socket
import threading
import time
from typing import Callable

from node_reader.blueapro_client import parse_push_payload
from node_reader.payload_diagnose import diagnose_payload

LogFn = Callable[[str, str, str], None]
OnDevices = Callable[[list], None]


class UdpIngestServer:
    """Receive BlueApro BLE scan datagrams (Raw UDP Client on gateway)."""

    DEFAULT_PORT = 8765

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = DEFAULT_PORT,
        on_devices: OnDevices | None = None,
        log: LogFn | None = None,
    ):
        self.host = host
        self.port = port
        self.on_devices = on_devices
        self.log = log or (lambda _d, _c, _m: None)
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.packet_count = 0
        self._warned_sources: set[str] = set()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> tuple[bool, str]:
        if self.running:
            return True, f"UDP already listening on {self.port}"
        self._stop.clear()
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind((self.host, self.port))
            self._sock.settimeout(1.0)
        except OSError as e:
            return False, f"UDP bind failed: {e}"
        self._thread = threading.Thread(target=self._loop, daemon=True, name="UdpIngest")
        self._thread.start()
        self.log("OUT", "UDP", f"Listening udp://{self.host}:{self.port}")
        return True, f"UDP listening on port {self.port}"

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _log_unparsed(self, data: bytes, src_ip: str) -> None:
        hint = diagnose_payload(data, src_ip)
        if src_ip not in self._warned_sources:
            self._warned_sources.add(src_ip)
            self.log("IN", "UDP", f"No tags — {hint}")
        elif self.packet_count <= 3 or self.packet_count % 20 == 0:
            self.log("IN", "UDP", f"No tags parsed ({len(data)} bytes from {src_ip})")

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                data, addr = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                continue
            self.packet_count += 1
            self.log("IN", "UDP", f"{len(data)} bytes from {addr[0]}:{addr[1]}")
            devices = parse_push_payload(data, "application/json")
            if self.on_devices and devices:
                for d in devices:
                    d.source = "udp"
                self.on_devices(devices)
            else:
                self._log_unparsed(data, addr[0])


class TcpIngestServer:
    """Receive BlueApro when gateway uses Raw TCP Client (connects to this PC)."""

    DEFAULT_PORT = 8766

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = DEFAULT_PORT,
        on_devices: OnDevices | None = None,
        log: LogFn | None = None,
    ):
        self.host = host
        self.port = port
        self.on_devices = on_devices
        self.log = log or (lambda _d, _c, _m: None)
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.message_count = 0
        self._warned_sources: set[str] = set()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> tuple[bool, str]:
        if self.running:
            return True, f"TCP already listening on {self.port}"
        self._stop.clear()
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind((self.host, self.port))
            self._sock.listen(8)
            self._sock.settimeout(1.0)
        except OSError as e:
            return False, f"TCP bind failed: {e}"
        self._thread = threading.Thread(target=self._accept_loop, daemon=True, name="TcpIngest")
        self._thread.start()
        self.log("OUT", "TCP", f"Listening tcp://{self.host}:{self.port}")
        return True, f"TCP listening on port {self.port}"

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._handle_client,
                args=(conn, addr),
                daemon=True,
            ).start()

    def _handle_client(self, conn: socket.socket, addr) -> None:
        self.log("IN", "TCP", f"Connection from {addr[0]}:{addr[1]}")
        buf = b""
        try:
            conn.settimeout(30.0)
            while not self._stop.is_set():
                chunk = conn.recv(65535)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self._process_payload(line, addr)
                if len(buf) > 512000:
                    self._process_payload(buf, addr)
                    buf = b""
            if buf.strip():
                self._process_payload(buf, addr)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _process_payload(self, data: bytes, addr) -> None:
        if not data.strip():
            return
        self.message_count += 1
        self.log("IN", "TCP", f"{len(data)} bytes from {addr[0]}")
        devices = parse_push_payload(data, "application/json")
        if self.on_devices and devices:
            for d in devices:
                d.source = "tcp"
            self.on_devices(devices)
        else:
            hint = diagnose_payload(data, addr[0])
            if addr[0] not in self._warned_sources:
                self._warned_sources.add(addr[0])
                self.log("IN", "TCP", f"No tags — {hint}")


# Recommended ports (no global standard — must match on BlueApro and PC)
RECOMMENDED_UDP_PORT = 8765
RECOMMENDED_TCP_PORT = 8766

BLUEAPRO_UDP_HINT = (
    "BlueApro web UI → Transport → Raw UDP Client\n"
    "  Host = your PC IP (shown below)\n"
    "  Port = {port}  (same as PC listen port)\n"
    "  Encoding = JSON Parsed (or JSON Raw)\n"
    "  Enable Send realtime"
)

BLUEAPRO_TCP_HINT = (
    "BlueApro web UI → Transport → Raw TCP Client\n"
    "  Host = your PC IP (shown below)\n"
    "  Port = {port}  (PC TCP listen port)\n"
    "  Encoding = JSON Parsed (or JSON Raw)\n"
    "  Enable Send realtime"
)
