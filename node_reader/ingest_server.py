"""Local HTTP server — receives BlueApro POST pushes and serves dashboard API."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import urlparse

from node_reader.blueapro_client import parse_push_payload

LogFn = Callable[[str, str, str], None]


@dataclass
class IngestState:
    devices: dict = field(default_factory=dict)
    log_lines: list = field(default_factory=list)
    last_push_at: float = 0.0
    push_count: int = 0


class IngestServer:
    """Threaded HTTP server for BlueApro push mode and local API."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        ingest_path: str = "/ingest/blueapro",
        on_devices: Callable[[list], None] | None = None,
        log: LogFn | None = None,
    ):
        self.host = host
        self.port = port
        self.ingest_path = ingest_path.rstrip("/") or "/ingest/blueapro"
        self.on_devices = on_devices
        self.log = log or (lambda _d, _c, _m: None)
        self.state = IngestState()
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self) -> tuple[bool, str]:
        if self.running:
            return True, "Already listening"
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass

            def _json_response(self, code: int, payload: dict):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = urlparse(self.path).path
                outer.log("IN", "LOCAL", f"GET {path}")
                if path == "/api/health":
                    outer._json_response(200, {
                        "ok": True,
                        "push_count": outer.state.push_count,
                        "devices": len(outer.state.devices),
                    })
                    return
                if path == "/api/tags":
                    outer._json_response(200, {
                        "items": [d for d in outer.state.devices.values()],
                    })
                    return
                if path in ("/", "/dashboard"):
                    html = (
                        "<html><head><title>HOLO Node Reader</title></head>"
                        "<body><h1>HOLO-RTLS Node Reader</h1>"
                        f"<p>BlueApro ingest: POST {outer.ingest_path}</p>"
                        f"<p>Devices: {len(outer.state.devices)} | Pushes: {outer.state.push_count}</p>"
                        "</body></html>"
                    ).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Length", str(len(html)))
                    self.end_headers()
                    self.wfile.write(html)
                    return
                self._json_response(404, {"error": "not found"})

            def do_POST(self):
                path = urlparse(self.path).path.rstrip("/")
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length else b""
                ct = self.headers.get("Content-Type", "")
                outer.log("IN", "LOCAL", f"POST {path} ({len(body)} bytes)")

                if path == outer.ingest_path.rstrip("/") or path.endswith("/ingest/blueapro"):
                    devices = parse_push_payload(body, ct)
                    outer.state.push_count += 1
                    outer.state.last_push_at = time.time()
                    for d in devices:
                        outer.state.devices[d.mac] = {
                            "mac": d.mac,
                            "name": d.name,
                            "rssi": d.rssi,
                            "scan_type": d.scan_type,
                            "source": d.source,
                            "last_seen": time.time(),
                        }
                    if outer.on_devices and devices:
                        outer.on_devices(devices)
                    outer._json_response(200, {"ok": True, "received": len(devices)})
                    return

                self._json_response(404, {"error": "not found"})

        try:
            self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        except OSError as e:
            return False, str(e)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True, name="IngestHTTP")
        self._thread.start()
        self.log("OUT", "LOCAL", f"Listening http://{self.host}:{self.port}{self.ingest_path}")
        return True, f"Listening on port {self.port}"

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
