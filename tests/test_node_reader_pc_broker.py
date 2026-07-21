"""Integration test for PC MQTT broker + capture plugin."""
import asyncio

from node_reader.capture_plugin import register_message_handler
from node_reader.mqtt_parse import parse_mqtt_payload


def test_broker_capture_and_parse():
    captured = []

    def handler(client_id, topic, payload):
        captured.append((client_id, topic, payload))

    register_message_handler(handler)

    async def run():
        from amqtt.broker import Broker

        config = {
            "listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:1887"}},
            "plugins": {
                "node_reader.capture_plugin.MessageCapturePlugin": {},
                "amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True},
            },
        }
        broker = Broker(config)
        await broker.start()
        import paho.mqtt.client as mqtt

        try:
            pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="wifi-node-test")
        except AttributeError:
            pub = mqtt.Client(client_id="wifi-node-test")
        pub.connect("127.0.0.1", 1887)
        pub.loop_start()
        payload = "00:C0:CA:A1:4B:18,F9:2F:B6:2C:DE:24,-72,98"
        pub.publish("rssi/data", payload, qos=0)
        await asyncio.sleep(0.8)
        pub.loop_stop()
        pub.disconnect()
        try:
            await asyncio.wait_for(broker.shutdown(), timeout=3.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass

    asyncio.run(run())
    assert captured, "expected capture plugin to receive publish"
    _cid, topic, body = captured[0]
    assert topic == "rssi/data"
    devices = parse_mqtt_payload(body, topic)
    assert len(devices) == 1
    assert devices[0].mac == "F9:2F:B6:2C:DE:24"
