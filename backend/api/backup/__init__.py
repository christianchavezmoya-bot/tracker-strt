"""Backup API — Phase 9 stub."""
from flask import Blueprint, request, jsonify, send_file, Response
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timezone
import os, sqlite3, io, gzip, shutil
from backend.extensions import db
from backend.models import BackupJob
from backend.utils.decorators import require_permission
from backend.services.rbac_service import Permission
from backend import config

backup_bp = Blueprint("backup", __name__, url_prefix="/api/backup")


@backup_bp.route("", methods=["GET"])
@jwt_required()
@require_permission(Permission.TRIGGER_BACKUP)
def list_backups():
    jobs = BackupJob.query.order_by(BackupJob.created_at.desc()).limit(50).all()
    return jsonify({"items": [j.to_dict() for j in jobs]})


@backup_bp.route("/trigger", methods=["POST"])
@jwt_required()
@require_permission(Permission.TRIGGER_BACKUP)
def trigger_backup():
    user_id = int(get_jwt_identity())
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"holo_rtls_backup_{ts}.db"
    filepath = config.BACKUP_DIR / filename

    job = BackupJob(
        filename=filename,
        status="running",
        trigger="manual",
        created_by_id=user_id,
    )
    db.session.add(job)
    db.session.commit()

    try:
        db_path = config.DATA_DIR / "holo_rtls.db"
        shutil.copy2(str(db_path), str(filepath))
        size = os.path.getsize(filepath)
        job.size_bytes = size
        job.status = "done"
        job.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({"job": job.to_dict()}), 200
    except Exception as e:
        job.status = "failed"
        job.notes = str(e)[:500]
        db.session.commit()
        return jsonify({"error": str(e), "job": job.to_dict()}), 500


@backup_bp.route("/<int:job_id>/download", methods=["GET"])
@jwt_required()
@require_permission(Permission.TRIGGER_BACKUP)
def download_backup(job_id):
    job = BackupJob.query.get_or_404(job_id)
    filepath = config.BACKUP_DIR / job.filename
    if not filepath.exists():
        return jsonify({"error": "Backup file not found"}), 404
    return send_file(
        filepath,
        as_attachment=True,
        download_name=job.filename,
        mimetype="application/x-sqlite3",
    )


@backup_bp.route("/<int:job_id>/restore", methods=["POST"])
@jwt_required()
@require_permission(Permission.RESTORE_BACKUP)
def restore_backup(job_id):
    job = BackupJob.query.get_or_404(job_id)
    filepath = config.BACKUP_DIR / job.filename
    if not filepath.exists():
        return jsonify({"error": "Backup file not found"}), 404
    # TODO: Validate backup integrity before restoring
    # For now: require confirmation flag
    body = request.get_json() or {}
    if not body.get("confirm"):
        return jsonify({"error": "Set confirm=true to restore from backup"}), 400
    db_path = config.DATA_DIR / "holo_rtls.db"
    shutil.copy2(str(filepath), str(db_path))
    return jsonify({"message": f"Restored from {job.filename} — restart required"})
