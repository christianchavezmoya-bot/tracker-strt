"""Capture MQTT publishes for the embedded HOLO-RTLS broker."""
from __future__ import annotations

from typing import Callable

from amqtt.broker import BrokerContext
from amqtt.plugins.base import BasePlugin
from amqtt.session import ApplicationMessage

MessageHandler = Callable[[str, str, str], None]
_handlers: list[MessageHandler] = []


def register_message_handler(handler: MessageHandler) -> None:
    _handlers.append(handler)


def clear_message_handlers() -> None:
    _handlers.clear()


class MessageCapturePlugin(BasePlugin[BrokerContext]):
    """Broker plugin — forwards every PUBLISH to registered handlers."""

    async def on_broker_client_connected(self, client_id: str, client_session=None) -> None:
        try:
            from backend.services.mqtt_client_registry import register_client
            addr = getattr(client_session, "remote_address", None)
            register_client(client_id or "?", str(addr) if addr else None)
        except Exception:
            pass

    async def on_broker_message_received(self, *, client_id: str, message: ApplicationMessage) -> None:
        topic = message.topic or ""
        data = message.data
        if isinstance(data, (bytes, bytearray)):
            payload = data.decode("utf-8", errors="replace")
        else:
            payload = str(data or "")
        for handler in list(_handlers):
            try:
                handler(client_id or "?", topic, payload)
            except Exception:
                pass
