"""
HOLO-RTLS — Hardware Profiles
Pre-defined configuration profiles for market-available hardware.
Each profile defines: required settings, defaults, validation rules,
and how to connect to the device.
"""
from dataclasses import dataclass, field
from typing import Optional
from backend.models.hardware import HardwareType, Protocol


@dataclass
class HardwareProfile:
    """
    A hardware device profile.
    Profiles are read-only — defined in code, not in the DB.
    """
    id: str                     # Unique identifier, e.g. "qorvo_dwm1001"
    name: str                  # Human name, e.g. "Qorvo DWM1001"
    vendor: str                # Manufacturer
    hardware_type: HardwareType
    protocol: Protocol
    description: str
    # Settings fields: each dict has: key, label, type, required, default, secret, help
    settings_fields: list = field(default_factory=list)
    # How to connect
    connection_help: str = ""
    # Whether the positioning engine supports this profile
    positioning_supported: bool = True
    # Example settings for the settings_json field
    example_settings: dict = field(default_factory=dict)


# ── Registry ────────────────────────────────────────────────────────────────
# All supported profiles. Import this dict to get the full catalog.
PROFILES: dict[str, HardwareProfile] = {}


def profile(
    id: str, name: str, vendor: str, hardware_type: HardwareType,
    protocol: Protocol, description: str, connection_help: str = "",
    positioning_supported: bool = True, **kwargs
):
    """Decorator to register a hardware profile."""
    def decorator(cls_or_func):
        p = HardwareProfile(
            id=id, name=name, vendor=vendor, hardware_type=hardware_type,
            protocol=protocol, description=description,
            connection_help=connection_help,
            positioning_supported=positioning_supported,
            **kwargs,
        )
        PROFILES[id] = p
        return cls_or_func
    return decorator


def _field(key, label, field_type="string", required=False, default=None,
           secret=False, help_text="", options=None):
    return dict(
        key=key, label=label, type=field_type,
        required=required, default=default,
        secret=secret, help_text=help_text, options=options,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  UWB — Ultra-Wideband
# ══════════════════════════════════════════════════════════════════════════════

@profile(
    id="qorvo_dwm1001",
    name="Qorvo DWM1001",
    vendor="Qorvo (formerly DecaWave)",
    hardware_type=HardwareType.UWB,
    protocol=Protocol.SERIAL,
    description="DWM1001 module — UWB + BLE combo. Most common for RTLS. "
               "Supports TDoA and Two-Way Ranging.",
    connection_help="Connect via USB-UART (CP2102) at 115200 baud. "
                    "Run tag firmware on modules. Use scanner.py pattern.",
    settings_fields=[
        _field("port",       "Serial Port",     "string", required=True,  default="/dev/ttyUSB0", help_text="e.g. /dev/ttyUSB0 or COM3"),
        _field("baud_rate",  "Baud Rate",       "select", required=True,  default="115200", options=["9600","19200","38400","57600","115200","921600"]),
        _field("firmware",   "Firmware Mode",   "select", required=False, default="tag", options=["tag","anchor","tag_twr","anchor_tdoa"]),
        _field("tx_power",   "TX Power (dBm)",  "int",    required=False, default="-20", help_text="-40 to +10 dBm"),
        _field("channel",    "UWB Channel",     "select", required=False, default="5",    options=["1","2","3","4","5","7"]),
        _field("poll_rate", "Poll Rate (ms)",   "int",    required=False, default="100",  help_text="Position update interval"),
    ],
    example_settings={"port": "/dev/ttyUSB0", "baud_rate": "115200", "firmware": "tag", "channel": "5"},
)
def qorvo_dwm1001():
    pass


@profile(
    id="decawave_dw1000",
    name="DecaWave DW1000",
    vendor="DecaWave",
    hardware_type=HardwareType.UWB,
    protocol=Protocol.SERIAL,
    description="Original DW1000 module. Requires external MCU. "
               "Supports TDoA, TWR, and PDOA.",
    connection_help="Connect via SPI to an ESP32 or STM32, then expose over UART.",
    settings_fields=[
        _field("port",      "Serial Port",    "string", required=True,  default="/dev/ttyUSB0"),
        _field("baud_rate", "Baud Rate",     "select", required=True,  default="115200", options=["9600","115200","921600"]),
        _field("antenna_delay", "Antenna Delay (raw)", "int", required=False, default="16384", help_text="Per-device calibration value"),
        _field("channel",   "UWB Channel",   "select", required=False, default="2",      options=["1","2","3","4","5","7"]),
    ],
    example_settings={"port": "/dev/ttyUSB0", "baud_rate": "115200", "channel": "2"},
)
def decawave_dw1000():
    pass


@profile(
    id="decawave_dw3000",
    name="DecaWave DW3000",
    vendor="Qorvo",
    hardware_type=HardwareType.UWB,
    protocol=Protocol.SERIAL,
    description="Next-gen DW3000. Lower power, better isolation, faster data rate. "
               "Compatible with DW1000 network.",
    connection_help="SPI to MCU → UART bridge. Same as DW1000.",
    settings_fields=[
        _field("port",       "Serial Port",   "string", required=True,  default="/dev/ttyUSB0"),
        _field("baud_rate",  "Baud Rate",    "select", required=True,  default="921600", options=["115200","460800","921600"]),
        _field("channel",    "UWB Channel",  "select", required=False, default="5",     options=["1","2","3","4","5","7"]),
        _field("prf",        "PRF (MHz)",    "select", required=False, default="64",    options=["16","64"]),
    ],
    example_settings={"port": "/dev/ttyUSB0", "baud_rate": "921600", "channel": "5"},
)
def decawave_dw3000():
    pass


@profile(
    id="sewio_uwb",
    name="Sewio RTLS",
    vendor="Sewio",
    hardware_type=HardwareType.UWB,
    protocol=Protocol.MQTT,
    description="Enterprise UWB RTLS. Hardware sold as complete system. "
               "Exposes position data via MQTT broker.",
    connection_help="Connect to Sewio MQTT broker. Configure topic subscription.",
    settings_fields=[
        _field("broker_host", "Broker Host",    "string", required=True,  default="192.168.1.100"),
        _field("broker_port", "Broker Port",   "int",    required=True,  default="1883"),
        _field("topic",       "MQTT Topic",    "string", required=True,  default="rtls/positions"),
        _field("username",    "Username",       "string", required=False),
        _field("password",    "Password",       "string", required=False, secret=True),
        _field("tls",         "Use TLS",        "bool",   required=False, default="false"),
        _field("qos",         "QoS Level",      "select", required=False, default="1", options=["0","1","2"]),
    ],
    example_settings={"broker_host": "192.168.1.100", "broker_port": 1883, "topic": "rtls/positions", "qos": "1"},
)
def sewio_uwb():
    pass


@profile(
    id="pozyx",
    name="Pozyx Creator",
    vendor="Pozyx",
    hardware_type=HardwareType.UWB,
    protocol=Protocol.SERIAL,
    description="Pozyx UWB Creator kit. Arduino-compatible. "
               "Good for prototyping RTLS.",
    connection_help="Connect via USB-Serial at 115200. Uses Pozyx Arduino library.",
    settings_fields=[
        _field("port",       "Serial Port",  "string", required=True,  default="/dev/ttyUSB0"),
        _field("baud_rate",  "Baud Rate",   "select", required=True,  default="115200", options=["9600","115200"]),
        _field("mode",       "Mode",         "select", required=False, default="tag", options=["tag","anchor","both"]),
    ],
    example_settings={"port": "/dev/ttyUSB0", "baud_rate": "115200", "mode": "tag"},
)
def pozyx():
    pass


# ══════════════════════════════════════════════════════════════════════════════
#  BLE — Bluetooth Low Energy
# ══════════════════════════════════════════════════════════════════════════════

@profile(
    id="generic_ibeacon",
    name="Generic iBeacon",
    vendor="Various",
    hardware_type=HardwareType.BLE,
    protocol=Protocol.BLE_GATT,
    description="Standard iBeacon format (UUID + Major + Minor). "
               "Most universal BLE beacon format.",
    connection_help="Scan with ESP32 or nRF52840 BLE gateway. "
                    "RSSI-based positioning (accuracy 3-10m).",
    settings_fields=[
        _field("scan_interval_ms",  "Scan Interval (ms)", "int", required=False, default="100"),
        _field("rssi_filter",      "Min RSSI (dBm)",     "int",  required=False, default="-90"),
        _field("uuid_filter",      "iBeacon UUID Filter", "string", required=False, help_text="Filter by beacon UUID (optional)"),
    ],
    example_settings={"scan_interval_ms": 100, "rssi_filter": -90},
)
def generic_ibeacon():
    pass


@profile(
    id="ruuvi_tag",
    name="Ruuvi Tag",
    vendor="Ruuvi Innovations",
    hardware_type=HardwareType.BLE,
    protocol=Protocol.BLE_GATT,
    description="BLE environmental sensor. Temperature, humidity, pressure, "
               "accelerometer. Broadcasts via BLE advertising.",
    connection_help="Scan with ESP32/nRF52 BLE gateway. "
                    "Ruuvi shows data directly in BLE scan.",
    settings_fields=[
        _field("rssi_filter",    "Min RSSI (dBm)",        "int",    required=False, default="-90"),
        _field("scan_interval_ms", "Scan Interval (ms)", "int",    required=False, default="1000"),
        _field("format",         "Data Format",           "select", required=False, default="RAWv2", options=["RAWv1","RAWv2","URL"]),
        _field("mac_whitelist",   "MAC Whitelist",         "string", required=False, help_text="Comma-separated MACs to track"),
    ],
    example_settings={"rssi_filter": -90, "scan_interval_ms": 1000, "format": "RAWv2"},
)
def ruuvi_tag():
    pass


@profile(
    id="sensirion_sen5x",
    name="Sensirion SEN5x",
    vendor="Sensirion",
    hardware_type=HardwareType.ENVIRO,
    protocol=Protocol.I2C,
    description="Environmental sensor. PM2.5, VOC, NO2, temperature, humidity. "
               "Used for air quality monitoring zones.",
    connection_help="I2C connection to ESP32 or Raspberry Pi. "
                    "Use Sensirion SEN5x Arduino/Python library.",
    settings_fields=[
        _field("i2c_address",  "I2C Address",        "string", required=False, default="0x69"),
        _field("bus",          "I2C Bus",             "string", required=False, default="/dev/i2c-1"),
        _field("read_interval","Read Interval (s)",    "int",   required=False, default="5"),
    ],
    example_settings={"i2c_address": "0x69", "bus": "/dev/i2c-1", "read_interval": 5},
)
def sensirion_sen5x():
    pass


@profile(
    id="esp32_ble_gateway",
    name="ESP32 BLE Gateway",
    vendor="Espressif",
    hardware_type=HardwareType.BLE,
    protocol=Protocol.MQTT,
    description="ESP32 as BLE scanner gateway. Scans nearby BLE devices "
               "and publishes RSSI data to MQTT.",
    connection_help="Flash ESP32 with BLE gateway firmware. "
                    "Device publishes to your MQTT broker.",
    settings_fields=[
        _field("broker_host",  "Broker Host",   "string", required=True,  default="192.168.1.10"),
        _field("broker_port",  "Broker Port",   "int",   required=True,  default="1883"),
        _field("mqtt_topic",  "MQTT Topic",    "string", required=True, default="ble/rssi"),
        _field("wifi_ssid",   "WiFi SSID",     "string", required=False),
        _field("wifi_password","WiFi Password",  "string", required=False, secret=True),
        _field("scan_duration_ms","Scan Duration (ms)","int", required=False, default="5000"),
    ],
    example_settings={"broker_host": "192.168.1.10", "broker_port": 1883, "mqtt_topic": "ble/rssi"},
)
def esp32_ble_gateway():
    pass


# ══════════════════════════════════════════════════════════════════════════════
#  WiFi RSSI
# ══════════════════════════════════════════════════════════════════════════════

@profile(
    id="esp32_wifi_scanner",
    name="ESP32 WiFi Scanner",
    vendor="Espressif",
    hardware_type=HardwareType.WIFI,
    protocol=Protocol.MQTT,
    description="ESP32 as WiFi scanner. Detects nearby APs and mobile devices. "
               "Less accurate than UWB but requires no special hardware.",
    connection_help="Flash ESP32 with WiFi scanner firmware. "
                    "Device publishes RSSI to MQTT.",
    settings_fields=[
        _field("broker_host",  "Broker Host",    "string", required=True,  default="192.168.1.10"),
        _field("broker_port",  "Broker Port",    "int",   required=True,  default="1883"),
        _field("mqtt_topic",  "MQTT Topic",    "string", required=True, default="wifi/rssi"),
        _field("scan_interval","Scan Interval (s)","int", required=False, default="3"),
    ],
    example_settings={"broker_host": "192.168.1.10", "mqtt_topic": "wifi/rssi", "scan_interval": 3},
)
def esp32_wifi_scanner():
    pass


# ══════════════════════════════════════════════════════════════════════════════
#  Multi-Protocol / Aggregator
# ══════════════════════════════════════════════════════════════════════════════

@profile(
    id="custom_mqtt",
    name="Custom MQTT Source",
    vendor="Custom / Other",
    hardware_type=HardwareType.UWB,   # Could be any
    protocol=Protocol.MQTT,
    description="Connect any device that publishes position data to MQTT. "
               "Configure the payload format to match your device.",
    connection_help="Configure MQTT broker credentials and define the "
                    "payload mapping to HOLO-RTLS fields.",
    settings_fields=[
        _field("broker_host",  "Broker Host",    "string", required=True),
        _field("broker_port",  "Broker Port",  "int",    required=True,  default="1883"),
        _field("username",     "Username",      "string", required=False),
        _field("password",    "Password",      "string", required=False, secret=True),
        _field("tls",          "Use TLS",       "bool",  required=False, default="false"),
        _field("topic",        "MQTT Topic",    "string", required=True),
        _field("payload_format", "Payload Format", "select", required=True, default="json",
               options=["json","csv","custom"]),
        _field("field_mapping", "Field Mapping", "json", required=True,
               default='{"tag_id": "mac", "x": "x", "y": "y", "z": "z", "rssi": "rssi"}',
               help_text='JSON: map source fields to HOLO-RTLS fields'),
    ],
    example_settings={
        "broker_host": "192.168.1.10", "topic": "positions/data",
        "payload_format": "json",
        "field_mapping": '{"tag_id": "mac", "x": "x", "y": "y", "rssi": "rssi"}',
    },
)
def custom_mqtt():
    pass


@profile(
    id="mock_data",
    name="Mock / Simulator",
    vendor="HOLO-RTLS",
    hardware_type=HardwareType.UWB,
    protocol=Protocol.SERIAL,
    description="Simulated positioning data for testing without hardware. "
               "Generates synthetic RSSI and position data.",
    connection_help="No hardware needed. Enable mock mode in config. "
                    "Used for development and demo.",
    settings_fields=[
        _field("num_tags",      "Number of Tags",       "int", required=False, default="5"),
        _field("num_anchors",   "Number of Anchors",    "int", required=False, default="4"),
        _field("update_rate_ms","Update Rate (ms)",     "int", required=False, default="500"),
        _field("noise_std",    "Noise Std Dev (m)",   "float", required=False, default="0.1"),
        _field("tag_movement",  "Tag Movement Mode",   "select", required=False, default="random_walk",
               options=["static", "random_walk", "path_follow"]),
    ],
    example_settings={"num_tags": 5, "num_anchors": 4, "update_rate_ms": 500, "noise_std": 0.1},
    positioning_supported=True,
)
def mock_data():
    pass


# ── Registry is built on module load via the @profile decorator ──────────────
# Access profiles with: PROFILES["qorvo_dwm1001"]
# List all profiles: list(PROFILES.values())


def get_profiles_by_type(hardware_type: HardwareType) -> list[HardwareProfile]:
    """Return all profiles matching a hardware type."""
    return [p for p in PROFILES.values() if p.hardware_type == hardware_type]


def get_profile(profile_id: str) -> Optional[HardwareProfile]:
    """Get a single profile by ID."""
    return PROFILES.get(profile_id)
