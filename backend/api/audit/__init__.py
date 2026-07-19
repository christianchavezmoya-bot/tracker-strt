"""Audit API — Phase 8 stub."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from backend.models import AuditLog
from backend.utils.decorators import require_permission
from backend.services.rbac_service import Permission

audit_bp = Blueprint("audit", __name__, url_prefix="/api/audit")


@audit_bp.route("", methods=["GET"])
@jwt_required()
@require_permission(Permission.VIEW_AUDIT)
def list_logs():
    q = AuditLog.query
    if request.args.get("action"):
        q = q.filter_by(action=request.args["action"])
    if request.args.get("entity_type"):
        q = q.filter_by(entity_type=request.args["entity_type"])
    if request.args.get("user_id"):
        q = q.filter_by(user_id=int(request.args["user_id"]))
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    pagination = q.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    return jsonify({
        "items": [a.to_dict() for a in pagination.items],
        "total": pagination.total, "page": page,
        "per_page": per_page, "pages": pagination.pages,
    })


@audit_bp.route("/export", methods=["GET"])
@jwt_required()
@require_permission(Permission.VIEW_AUDIT)
def export_logs():
    """Server-side CSV export of audit logs (up to 10k rows)."""
    import csv
    import io
    from flask import Response

    q = AuditLog.query
    if request.args.get("action"):
        q = q.filter_by(action=request.args["action"])
    if request.args.get("entity_type"):
        q = q.filter_by(entity_type=request.args["entity_type"])
    if request.args.get("user_id"):
        q = q.filter_by(user_id=int(request.args["user_id"]))
    rows = q.order_by(AuditLog.timestamp.desc()).limit(10000).all()
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[
        "id", "timestamp", "user_id", "action", "entity_type", "entity_id", "ip_address", "details"
    ])
    writer.writeheader()
    for a in rows:
        d = a.to_dict()
        writer.writerow({
            "id": d.get("id"),
            "timestamp": d.get("timestamp"),
            "user_id": d.get("user_id"),
            "action": d.get("action"),
            "entity_type": d.get("entity_type"),
            "entity_id": d.get("entity_id"),
            "ip_address": d.get("ip_address"),
            "details": d.get("details"),
        })
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit_export.csv"'},
    )
