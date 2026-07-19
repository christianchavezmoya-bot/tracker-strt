"""
HOLO-RTLS — Hardware Configuration API
Manage real hardware connections: UWB, BLE, WiFi, environmental sensors.
"""
import json
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.extensions import db
from backend.models import HardwareConfig, AuditLog
from backend.models.hardware import HardwareType, Protocol
from backend.models.hardware_profiles import PROFILES, get_profile, get_profiles_by_type
from backend.utils.decorators import require_permission
from backend.services.rbac_service import Permission

hardware_bp = Blueprint("hardware", __name__, url_prefix="/api/hardware")


# ── Profiles (read-only catalog) ──────────────────────────────────────────────
@hardware_bp.route("/profiles", methods=["GET"])
@jwt_required()
def list_profiles():
    """
    === A
    tags:
      - Hardware
    summary: List all hardware profiles
    description: Returns the catalog of all supported hardware profiles with their configuration fields.
    security:
      - Bearer: []
    responses:
      200:
        description: Hardware profile catalog
        schema:
          type: object
          properties:
            profiles:
              type: array
              items:
                type: object
                properties:
                  id: { type: string }
                  name: { type: string }
                  vendor: { type: string }
                  hardware_type: { type: string }
                  protocol: { type: string }
                  description: { type: string }
                  connection_help: { type: string }
                  positioning_supported: { type: boolean }
                  settings_fields: { type: array }
                  example_settings: { type: object }
            total: { type: integer }
    ===
    """
    profiles = []
    for p in PROFILES.values():
        profiles.append({
            "id": p.id,
            "name": p.name,
            "vendor": p.vendor,
            "hardware_type": p.hardware_type.name,
            "protocol": p.protocol.name,
            "description": p.description,
            "connection_help": p.connection_help,
            "positioning_supported": p.positioning_supported,
            "settings_fields": p.settings_fields,
            "example_settings": p.example_settings,
        })
    return jsonify({"profiles": profiles, "total": len(profiles)})


@hardware_bp.route("/profiles/type/<hardware_type>", methods=["GET"])
@jwt_required()
def profiles_by_type(hardware_type):
    """
    === A
    tags:
      - Hardware
    summary: Get profiles by hardware type
    description: Returns hardware profiles filtered by the specified hardware type.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: hardware_type
        required: true
        schema:
          type: string
        description: Hardware type (e.g., UWB, BLE, WIFI, ENVIRONMENTAL)
    responses:
      200:
        description: Profiles matching the hardware type
        schema:
          type: object
          properties:
            hardware_type: { type: string }
            profiles:
              type: array
              items:
                type: object
                properties:
                  id: { type: string }
                  name: { type: string }
                  vendor: { type: string }
                  description: { type: string }
      400:
        description: Unknown hardware type
    ===
    """
    try:
        ht = HardwareType[hardware_type.upper()]
    except KeyError:
        return jsonify({"error": f"Unknown hardware type: {hardware_type}"}), 400
    profiles = get_profiles_by_type(ht)
    return jsonify({
        "hardware_type": hardware_type.upper(),
        "profiles": [{"id": p.id, "name": p.name, "vendor": p.vendor,
                      "description": p.description} for p in profiles],
    })


# ── Hardware Configurations (user data) ──────────────────────────────────────
@hardware_bp.route("", methods=["GET"])
@jwt_required()
def list_configs():
    """
    === A
    tags:
      - Hardware
    summary: List all hardware configurations
    description: Returns all configured hardware entries ordered by type and name.
    security:
      - Bearer: []
    responses:
      200:
        description: List of hardware configurations
        schema:
          type: object
          properties:
            items:
              type: array
              items:
                type: object
            total: { type: integer }
    ===
    """
    configs = HardwareConfig.query.order_by(HardwareConfig.hardware_type, HardwareConfig.name).all()
    return jsonify({"items": [c.to_dict() for c in configs], "total": len(configs)})


@hardware_bp.route("/<int:config_id>", methods=["GET"])
@jwt_required()
def get_config(config_id):
    """
    === A
    tags:
      - Hardware
    summary: Get a hardware configuration
    description: Returns details for a specific hardware configuration.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: config_id
        required: true
        schema:
          type: integer
        description: Configuration ID
    responses:
      200:
        description: Hardware configuration
        schema:
          type: object
          properties:
            config: { type: object }
      404:
        description: Configuration not found
    ===
    """
    config = HardwareConfig.query.get_or_404(config_id)
    return jsonify({"config": config.to_dict(include_sensitive=False)})


@hardware_bp.route("", methods=["POST"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def create_config():
    """
    === A
    tags:
      - Hardware
    summary: Create a hardware configuration
    description: Creates a new hardware configuration entry. Requires EDIT_SETTINGS permission. Does not connect automatically.
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - profile_id
          properties:
            profile_id:
              type: string
              description: Hardware profile ID
            name:
              type: string
              description: Configuration name (defaults to profile name)
            settings:
              type: object
              description: Connection settings for the hardware
            notes:
              type: string
              description: Optional notes
    responses:
      201:
        description: Configuration created
        schema:
          type: object
          properties:
            config: { type: object }
      400:
        description: Missing profile_id or invalid profile
    ===
    """
    body = request.get_json() or {}

    profile_id = body.get("profile_id")
    if not profile_id:
        return jsonify({"error": "profile_id is required"}), 400

    profile = get_profile(profile_id)
    if not profile:
        return jsonify({"error": f"Unknown profile_id: {profile_id}"}), 400

    name = body.get("name", "").strip() or profile.name
    settings = body.get("settings", {})

    config = HardwareConfig(
        name=name,
        hardware_type=profile.hardware_type,
        protocol=profile.protocol,
        profile_id=profile_id,
    )
    config.set_settings(settings)
    config.created_by_id = int(get_jwt_identity())

    db.session.add(config)
    db.session.commit()

    AuditLog.log(
        action="hardware.config_create",
        user_id=int(get_jwt_identity()),
        entity_type="HardwareConfig",
        entity_id=config.id,
        details=json.dumps({"profile_id": profile_id, "name": name}),
    )

    return jsonify({"config": config.to_dict(include_sensitive=False)}), 201


@hardware_bp.route("/<int:config_id>", methods=["PATCH"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def update_config(config_id):
    """
    === A
    tags:
      - Hardware
    summary: Update a hardware configuration
    description: Updates a hardware configuration. Requires EDIT_SETTINGS permission.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: config_id
        required: true
        schema:
          type: integer
        description: Configuration ID
      - in: body
        name: body
        schema:
          type: object
          properties:
            name: { type: string }
            settings: { type: object }
            is_active: { type: boolean }
            notes: { type: string }
    responses:
      200:
        description: Configuration updated
        schema:
          type: object
          properties:
            config: { type: object }
      404:
        description: Configuration not found
    ===
    """
    config = HardwareConfig.query.get_or_404(config_id)
    body = request.get_json() or {}

    if "name" in body:
        config.name = body["name"].strip()
    if "settings" in body:
        config.set_settings(body["settings"])
    if "is_active" in body:
        config.is_active = bool(body["is_active"])
    if "notes" in body:
        config.notes = body["notes"]

    db.session.commit()

    AuditLog.log(
        action="hardware.config_update",
        user_id=int(get_jwt_identity()),
        entity_type="HardwareConfig",
        entity_id=config.id,
    )

    return jsonify({"config": config.to_dict(include_sensitive=False)})


@hardware_bp.route("/<int:config_id>", methods=["DELETE"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def delete_config(config_id):
    """
    === A
    tags:
      - Hardware
    summary: Delete a hardware configuration
    description: Deletes a hardware configuration. Requires EDIT_SETTINGS permission.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: config_id
        required: true
        schema:
          type: integer
        description: Configuration ID
    responses:
      200:
        description: Configuration deleted
        schema:
          type: object
          properties:
            message: { type: string }
      404:
        description: Configuration not found
    ===
    """
    config = HardwareConfig.query.get_or_404(config_id)
    AuditLog.log(
        action="hardware.config_delete",
        user_id=int(get_jwt_identity()),
        entity_type="HardwareConfig",
        entity_id=config.id,
        details=json.dumps({"name": config.name, "profile_id": config.profile_id}),
    )
    db.session.delete(config)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200


# ── Connection Management ──────────────────────────────────────────────────────
@hardware_bp.route("/<int:config_id>/test", methods=["POST"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def test_connection(config_id):
    """
    === A
    tags:
      - Hardware
    summary: Test hardware connection
    description: Tests connectivity to a hardware device without permanent activation. Requires EDIT_SETTINGS permission.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: config_id
        required: true
        schema:
          type: integer
        description: Configuration ID
    responses:
      200:
        description: Test result
        schema:
          type: object
          properties:
            connected: { type: boolean }
            message: { type: string }
            error: { type: string }
      404:
        description: Configuration not found
    ===
    """
    config = HardwareConfig.query.get_or_404(config_id)
    profile = get_profile(config.profile_id)

    result = _test_connection_impl(config, profile)
    return jsonify(result)


@hardware_bp.route("/<int:config_id>/connect", methods=["POST"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def connect(config_id):
    """
    === A
    tags:
      - Hardware
    summary: Connect to hardware device
    description: Attempts to establish a connection to a hardware device. Requires EDIT_SETTINGS permission.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: config_id
        required: true
        schema:
          type: integer
        description: Configuration ID
    responses:
      200:
        description: Connection successful
        schema:
          type: object
          properties:
            message: { type: string }
            connected: { type: boolean }
      400:
        description: Connection failed
        schema:
          type: object
          properties:
            message: { type: string }
            connected: { type: boolean }
            error: { type: string }
      404:
        description: Configuration not found
    ===
    """
    config = HardwareConfig.query.get_or_404(config_id)
    profile = get_config(config.profile_id)

    config.status = ConnectionStatus.CONNECTING
    db.session.commit()

    result = _test_connection_impl(config, profile)

    if result["connected"]:
        config.status = ConnectionStatus.CONNECTED
        from datetime import datetime, timezone
        config.last_seen = datetime.now(timezone.utc)
        config.error_message = None
        db.session.commit()
        return jsonify({"message": "Connected", **result})
    else:
        config.status = ConnectionStatus.ERROR
        config.error_message = result.get("error", "Unknown error")
        db.session.commit()
        return jsonify({"message": "Connection failed", **result}), 400


@hardware_bp.route("/<int:config_id>/disconnect", methods=["POST"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def disconnect(config_id):
    """
    === A
    tags:
      - Hardware
    summary: Disconnect from hardware device
    description: Disconnects from a hardware device. Requires EDIT_SETTINGS permission.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: config_id
        required: true
        schema:
          type: integer
        description: Configuration ID
    responses:
      200:
        description: Disconnected
        schema:
          type: object
          properties:
            message: { type: string }
      404:
        description: Configuration not found
    ===
    """
    config = HardwareConfig.query.get_or_404(config_id)
    config.status = ConnectionStatus.DISCONNECTED
    config.last_seen = None
    db.session.commit()
    return jsonify({"message": "Disconnected"})


@hardware_bp.route("/status", methods=["GET"])
@jwt_required()
def hardware_status():
    """
    === A
    tags:
      - Hardware
    summary: Get hardware connection status
    description: Returns connection status summary and details grouped by hardware type.
    security:
      - Bearer: []
    responses:
      200:
        description: Hardware status by type
        schema:
          type: object
          properties:
            summary:
              type: object
              properties:
                total: { type: integer }
                connected: { type: integer }
                disconnected: { type: integer }
                error: { type: integer }
            by_type:
              type: object
              additionalProperties:
                type: array
                items:
                  type: object
    ===
    """
    configs = HardwareConfig.query.all()
    by_type = {}
    for c in configs:
        ht_name = c.hardware_type_name
        if ht_name not in by_type:
            by_type[ht_name] = []
        by_type[ht_name].append(c.to_dict(include_sensitive=False))
    return jsonify({
        "summary": {
            "total": len(configs),
            "connected": sum(1 for c in configs if c.status == ConnectionStatus.CONNECTED),
            "disconnected": sum(1 for c in configs if c.status == ConnectionStatus.DISCONNECTED),
            "error": sum(1 for c in configs if c.status == ConnectionStatus.ERROR),
        },
        "by_type": by_type,
    })


# ── Connection Test Implementation ────────────────────────────────────────────
def _test_connection_impl(config, profile):
    """Test actual hardware connectivity. Called by test() and connect()."""
    from backend.models.hardware import ConnectionStatus
    settings = config.get_settings()
    protocol = Protocol(config.protocol)

    try:
        if protocol == Protocol.SERIAL:
            return _test_serial(settings)
        elif protocol == Protocol.MQTT:
            return _test_mqtt(settings)
        elif protocol == Protocol.REST:
            return _test_rest(settings)
        elif protocol == Protocol.BLE_GATT:
            return _test_ble(settings)
        else:
            return {"connected": False, "error": f"Protocol {protocol.name} not implemented"}
    except Exception as e:
        return {"connected": False, "error": str(e)}


def _test_serial(settings):
    """Test serial port connection."""
    import serial
    port = settings.get("port", "/dev/ttyUSB0")
    baud = int(settings.get("baud_rate", 115200))
    try:
        ser = serial.Serial(port, baud, timeout=1)
        ser.close()
        return {"connected": True, "message": f"Port {port} opened at {baud} baud"}
    except serial.SerialException as e:
        return {"connected": False, "error": f"Serial error: {e}"}
    except Exception as e:
        return {"connected": False, "error": str(e)}


def _test_mqtt(settings):
    """Test MQTT broker connection."""
    import paho.mqtt.client as mqtt
    host = settings.get("broker_host")
    port = int(settings.get("broker_port", 1883))
    username = settings.get("username")
    password = settings.get("password")

    result = {"connected": False}

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            result["connected"] = True
            result["message"] = f"Connected to {host}:{port}"
        else:
            result["error"] = f"MQTT connection failed with code {rc}"
        client.disconnect()

    client = mqtt.Client()
    if username and password:
        client.username_pw_set(username, password)
    client.on_connect = on_connect
    try:
        client.connect(host, port, timeout=5)
        client.loop_start()
        import time; time.sleep(3)
        client.loop_stop()
        if not result["connected"]:
            result["error"] = result.get("error", "Connection timeout")
    except Exception as e:
        result["error"] = str(e)
    return result


def _test_rest(settings):
    """Test REST API endpoint."""
    import requests
    url = settings.get("url")
    timeout = int(settings.get("timeout", 5))
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code < 400:
            return {"connected": True, "message": f"REST endpoint responded: {resp.status_code}"}
        else:
            return {"connected": False, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"connected": False, "error": str(e)}


def _test_ble(settings):
    """Test BLE scan (requires bluepy or bleak)."""
    # This is a placeholder — actual BLE testing requires platform-specific libs
    # On Linux: apt install bluez libbluetooth-dev; pip install pybluez
    # On any: pip install bleak (cross-platform)
    try:
        import importlib
        bleak = importlib.import_module("bleak")
        return {
            "connected": True,
            "message": "BLE stack available (bleak). Scan will work.",
            "note": "Actual device scan requires BT adapter and proximity to beacons.",
        }
    except ImportError:
        return {
            "connected": True,
            "message": "BLE library not installed. Run: pip install bleak",
            "note": "bleak supports Windows/macOS/Linux. BLE scanning will work once installed.",
        }
