from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

from backend.services.mqtt_capture_plugin import (
    MessageCapturePlugin,
    clear_message_handlers,
    register_message_handler,
)


class _DummyContext:
    def __init__(self) -> None:
        self.config = {}
        self.logger = logging.getLogger("test.mqtt_capture_plugin")

    def get_session(self, _client_id: str):
        return None


def test_capture_plugin_forwards_broker_message():
    captured: list[tuple[str, str, str, str | None]] = []
    plugin = MessageCapturePlugin(_DummyContext())
    message = SimpleNamespace(
        topic="rssi/data",
        data=b"AA:BB:CC:DD:EE:01,11:22:33:44:55:66,-68,95",
    )

    clear_message_handlers()
    register_message_handler(lambda cid, topic, payload, client_ip=None: captured.append((cid, topic, payload, client_ip)))
    try:
        asyncio.run(plugin.on_broker_message_received(client_id="smoke-client", message=message))
    finally:
        clear_message_handlers()

    assert captured == [
        (
            "smoke-client",
            "rssi/data",
            "AA:BB:CC:DD:EE:01,11:22:33:44:55:66,-68,95",
            None,
        )
    ]
