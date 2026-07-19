#!/usr/bin/env python3
"""SSE soak runner — validates stream stays alive for SSE_SOAK_SECONDS (default 8h)."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.getenv("HOLO_E2E_BASE", "http://127.0.0.1:8080").rstrip("/")
DURATION = int(os.getenv("SSE_SOAK_SECONDS", "28800"))
EMAIL = os.getenv("HOLO_E2E_EMAIL", "admin@holo-rtls.local")
PASSWORD = os.getenv("HOLO_E2E_PASSWORD", "ChangeMe123!")


def login() -> str:
    req = urllib.request.Request(
        f"{BASE}/api/auth/login",
        data=json.dumps({"email_or_username": EMAIL, "password": PASSWORD}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    token = data.get("access_token")
    if not token:
        raise RuntimeError("Login failed — no access_token")
    return token


def main() -> int:
    print(f"SSE soak: {DURATION}s against {BASE}/api/stream/positions")
    token = login()
    url = f"{BASE}/api/stream/positions?token={token}"
    req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})

    start = time.monotonic()
    deadline = start + DURATION
    events = 0
    heartbeats = 0
    errors = 0

    try:
        with urllib.request.urlopen(req, timeout=DURATION + 60) as resp:
            buffer = ""
            while time.monotonic() < deadline:
                chunk = resp.read(1024)
                if not chunk:
                    errors += 1
                    if errors > 5:
                        print("ERROR: stream closed unexpectedly")
                        return 1
                    time.sleep(1)
                    continue
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n\n" in buffer:
                    block, buffer = buffer.split("\n\n", 1)
                    if not block.strip():
                        continue
                    events += 1
                    if "heartbeat" in block or '"type": "heartbeat"' in block:
                        heartbeats += 1
                    elapsed = int(time.monotonic() - start)
                    if events % 50 == 0:
                        print(f"[{elapsed}s] events={events} heartbeats={heartbeats}")
    except urllib.error.HTTPError as e:
        print(f"ERROR: HTTP {e.code} — {e.read().decode()[:200]}")
        return 1
    except Exception as e:
        print(f"ERROR: {e}")
        return 1

    elapsed = int(time.monotonic() - start)
    print(f"PASS: {elapsed}s — events={events} heartbeats={heartbeats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
