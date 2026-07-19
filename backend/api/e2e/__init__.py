"""E2E-only helpers (registered when PLAYWRIGHT_E2E=1)."""
import os
from datetime import datetime, timezone

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from backend.extensions import db
from backend.models.alert import Alert, AlertType, AlertState

e2e_bp = Blueprint("e2e", __name__, url_prefix="/api/e2e")


def e2e_enabled() -> bool:
    return os.getenv("PLAYWRIGHT_E2E") == "1"


@e2e_bp.route("/seed-alert", methods=["POST"])
@jwt_required()
def seed_alert():
    if not e2e_enabled():
        return jsonify({"error": "Not found"}), 404
    alert = Alert(
        alert_type=int(AlertType.MANUAL),
        state=int(AlertState.ACTIVE),
        message="E2E smoke test alert — acknowledge me",
        triggered_at=datetime.now(timezone.utc),
    )
    db.session.add(alert)
    db.session.commit()
    return jsonify({"alert": alert.to_dict()}), 201


@e2e_bp.route("/alerts/<int:alert_id>", methods=["DELETE"])
@jwt_required()
def delete_alert(alert_id):
    if not e2e_enabled():
        return jsonify({"error": "Not found"}), 404
    alert = Alert.query.get(alert_id)
    if alert:
        db.session.delete(alert)
        db.session.commit()
    return jsonify({"deleted": True})
