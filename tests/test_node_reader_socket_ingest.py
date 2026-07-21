"""Tests for UDP/TCP ingest payload handling."""
import socket
import threading
import time

from node_reader.blueapro_client import parse_push_payload
from node_reader.socket_ingest import TcpIngestServer, UdpIngestServer


def test_udp_ingest_receives_json():
    received = []

    def on_devices(devs):
        received.extend(devs)

    srv = UdpIngestServer(host="127.0.0.1", port=18765, on_devices=on_devices)
    ok, _ = srv.start()
    assert ok
    try:
        payload = b'{"mac":"AA:BB:CC:DD:EE:01","rssi":-70,"name":"MOKO"}'
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(payload, ("127.0.0.1", 18765))
        sock.close()
        deadline = time.time() + 2.0
        while time.time() < deadline and not received:
            time.sleep(0.05)
        assert len(received) == 1
        assert received[0].mac == "AA:BB:CC:DD:EE:01"
        assert received[0].source == "udp"
    finally:
        srv.stop()


def test_tcp_ingest_receives_json_line():
    received = []

    def on_devices(devs):
        received.extend(devs)

    srv = TcpIngestServer(host="127.0.0.1", port=18766, on_devices=on_devices)
    ok, _ = srv.start()
    assert ok
    try:
        def send():
            time.sleep(0.1)
            conn = socket.create_connection(("127.0.0.1", 18766), timeout=2)
            conn.sendall(b'{"mac":"11:22:33:44:55:66","rssi":-80}\n')
            conn.close()

        threading.Thread(target=send, daemon=True).start()
        deadline = time.time() + 2.0
        while time.time() < deadline and not received:
            time.sleep(0.05)
        assert len(received) == 1
        assert received[0].source == "tcp"
    finally:
        srv.stop()


def test_parse_push_payload_single_object():
    devices = parse_push_payload(b'{"mac":"F9:2F:B6:2C:DE:24","rssi":-72}', "application/json")
    assert len(devices) == 1
