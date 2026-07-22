"""Capture MQTT publishes for the embedded HOLO-RTLS broker."""
from __future__ import annotations

from typing import Callable

from amqtt.broker import BrokerContext
from amqtt.plugins.base import BasePlugin
from amqtt.session import ApplicationMessage

MessageHandler = Callable[[str, str, str, str | None], None]
_handlers: list[MessageHandler] = []


def register_message_handler(handler: MessageHandler) -> None:
    _handlers.append(handler)


def clear_message_handlers() -> None:
    _handlers.clear()


def _session_client_ip(context: BrokerContext, client_id: str) -> str | None:
    try:
        session = context.get_session(client_id or "")
        if session:
            from backend.services.mqtt_client_registry import normalize_client_ip
            return normalize_client_ip(getattr(session, "remote_address", None))
    except Exception:
        pass
    return None


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
        cid = client_id or "?"
        client_ip = _session_client_ip(self.context, cid)
        try:
            from backend.services.mqtt_client_registry import register_client
            if client_ip:
                register_client(cid, client_ip)
        except Exception:
            pass
        for handler in list(_handlers):
            try:
                handler(cid, topic, payload, client_ip)
            except TypeError:
                # Back-compat for 3-arg handlers in tests
                try:
                    handler(cid, topic, payload)  # type: ignore[misc]
                except Exception:
                    pass
            except Exception:
                pass
