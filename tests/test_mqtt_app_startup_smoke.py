"""Smoke: Flask app starts with embedded MQTT broker enabled."""
import os
import socket
import time


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_app_starts_embedded_mqtt_broker():
    port = _free_port()
    os.environ["MQTT_BROKER_ENABLED"] = "1"
    os.environ["MQTT_BROKER_BIND"] = "127.0.0.1"
    os.environ["MQTT_BROKER_PORT"] = str(port)
    os.environ["MQTT_BROKER_HOST"] = "127.0.0.1"
    os.environ["HOLO_SKIP_INIT"] = "0"

    # Reload config module picks up env — create fresh app via factory path
    import importlib
    import backend.config as cfg
    importlib.reload(cfg)

    from backend.app import _init_positioning, create_app

    test_config = {
        "TESTING": True,
        "DEBUG": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
        "JWT_SECRET_KEY": "test-jwt-secret-key-for-testing-only-32chars",
        "SECRET_KEY": "test-secret-key-for-testing-only-32chars",
        "MAIL_SUPPRESS_SEND": True,
        "FLASK_MAIL_SUPPRESS_SEND": True,
    }
    # create_app skips _init_positioning when test_config is set — call manually
    app = create_app(test_config)
    with app.app_context():
        from backend.extensions import db
        db.create_all()
        _init_positioning(app)

    from backend.services.mqtt_broker_service import get_mqtt_broker

    broker = get_mqtt_broker()
    assert broker is not None, "broker singleton not initialized"
    assert broker.running, f"broker not running: {broker.last_error}"
    assert broker.port == port

    # Publish and verify broker increments counter
    import paho.mqtt.client as mqtt

    try:
        pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="startup-smoke")
    except AttributeError:
        pub = mqtt.Client(client_id="startup-smoke")
    pub.connect("127.0.0.1", port, keepalive=30)
    pub.loop_start()
    before = broker.message_count
    pub.publish("rssi/data", "00:11:22:33:44:55,AA:BB:CC:DD:EE:FF,-70,99", qos=0)
    deadline = time.time() + 5
    while time.time() < deadline and broker.message_count <= before:
        time.sleep(0.1)
    pub.loop_stop()
    pub.disconnect()
    broker.stop()
    assert broker.message_count > before, "broker did not receive publish during app startup smoke"

    os.environ.pop("MQTT_BROKER_ENABLED", None)
    importlib.reload(cfg)
