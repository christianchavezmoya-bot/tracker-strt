"""Embedded MQTT broker for HOLO-RTLS server (production WiFi node ingest)."""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable, Optional

from backend.services.mqtt_capture_plugin import clear_message_handlers, register_message_handler

logger = logging.getLogger(__name__)

LogFn = Callable[[str, str, str], None]
OnMessage = Callable[[str, str, str], None]  # client_id, topic, payload


class MqttBrokerService:
    """Run amqtt broker on the server (default 0.0.0.0:1883)."""

    DEFAULT_PORT = 1883

    def __init__(
        self,
        bind: str = "0.0.0.0",
        port: int = DEFAULT_PORT,
        allow_anonymous: bool = True,
        on_message: OnMessage | None = None,
        log: LogFn | None = None,
    ):
        self.bind = bind
        self.port = int(port)
        self.allow_anonymous = allow_anonymous
        self.on_message = on_message
        self.log = log or (lambda _d, _c, _m: None)
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._broker = None
        self._stop = threading.Event()
        self.message_count = 0
        self.client_count = 0
        self.last_error: Optional[str] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def bind_address(self) -> str:
        return f"{self.bind}:{self.port}"

    def start(self) -> tuple[bool, str]:
        if self.running:
            return True, f"Broker already running on port {self.port}"
        self._stop.clear()
        ready = threading.Event()
        result: dict = {"ok": False, "msg": ""}

        def _handler(client_id: str, topic: str, payload: str) -> None:
            self.message_count += 1
            self.log("IN", "MQTT", f"{client_id} → {topic}: {payload[:200]}")
            if self.on_message:
                self.on_message(client_id, topic, payload)

        register_message_handler(_handler)
        bind_addr = f"{self.bind}:{self.port}"

        def run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            config = {
                "listeners": {
                    "default": {
                        "type": "tcp",
                        "bind": bind_addr,
                    },
                },
                "plugins": {
                    "backend.services.mqtt_capture_plugin.MessageCapturePlugin": {},
                    "amqtt.plugins.authentication.AnonymousAuthPlugin": {
                        "allow_anonymous": self.allow_anonymous,
                    },
                },
            }
            try:
                from amqtt.broker import Broker

                broker = Broker(config, loop=loop)
                self._broker = broker
                loop.run_until_complete(broker.start())
                result["ok"] = True
                result["msg"] = f"MQTT broker listening on {bind_addr}"
                self.log("OUT", "MQTT", result["msg"])
                logger.info(result["msg"])
                ready.set()
                while not self._stop.is_set():
                    loop.run_until_complete(asyncio.sleep(0.25))
                if self._broker:
                    try:
                        loop.run_until_complete(asyncio.wait_for(self._broker.shutdown(), timeout=2.0))
                    except Exception:
                        pass
            except OSError as e:
                result["msg"] = f"Broker bind failed ({bind_addr}): {e}"
                self.last_error = result["msg"]
                self.log("IN", "MQTT", result["msg"])
                logger.error(result["msg"])
                ready.set()
            except Exception as e:
                result["msg"] = f"Broker error: {e}"
                self.last_error = result["msg"]
                self.log("IN", "MQTT", result["msg"])
                logger.exception("MQTT broker failed")
                ready.set()
            finally:
                clear_message_handlers()
                try:
                    loop.close()
                except Exception:
                    pass
                self._loop = None
                self._broker = None

        self._thread = threading.Thread(target=run, daemon=True, name="HoloMqttBroker")
        self._thread.start()
        ready.wait(timeout=8)
        if not result["ok"]:
            self.stop()
            return False, result.get("msg") or "Broker failed to start"
        return True, result["msg"]

    def stop(self) -> None:
        self._stop.set()
        clear_message_handlers()
        if self._thread:
            self._thread.join(timeout=6)
            self._thread = None

    def status(self) -> dict:
        return {
            "running": self.running,
            "bind": self.bind_address,
            "message_count": self.message_count,
            "last_error": self.last_error,
        }


_broker: Optional[MqttBrokerService] = None


def get_mqtt_broker() -> Optional[MqttBrokerService]:
    return _broker


def init_mqtt_broker(**kwargs) -> MqttBrokerService:
    global _broker
    if _broker is None:
        _broker = MqttBrokerService(**kwargs)
    return _broker
