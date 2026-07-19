"""Backup API — Phase 9 stub."""
from flask import Blueprint, request, jsonify, send_file, Response
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timezone
from pathlib import Path
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
    """
    === A
    tags:
      - Backup
    summary: List backup jobs
    description: Returns the list of backup jobs ordered by creation date. Requires TRIGGER_BACKUP permission.
    security:
      - Bearer: []
    responses:
      200:
        description: List of backup jobs
        schema:
          type: object
          properties:
            items:
              type: array
              items:
                type: object
    ===
    """
    jobs = BackupJob.query.order_by(BackupJob.created_at.desc()).limit(50).all()
    return jsonify({"items": [j.to_dict() for j in jobs]})


def _create_backup_file(trigger: str = "manual", user_id: int = None):
    """Shared backup implementation for manual + scheduled triggers."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"holo_rtls_backup_{ts}.db"
    filepath = config.BACKUP_DIR / filename

    job = BackupJob(
        filename=filename,
        status="running",
        trigger=trigger,
        created_by_id=user_id,
    )
    db.session.add(job)
    db.session.commit()

    try:
        # Prefer configured URI path; fall back to data dir
        uri = str(config.SQLALCHEMY_DATABASE_URI or "")
        if uri.startswith("sqlite:////"):
            db_path = uri.replace("sqlite:////", "/", 1)
        elif uri.startswith("sqlite:///"):
            db_path = uri.replace("sqlite:///", "", 1)
        else:
            db_path = str(config.DATA_DIR / "holo_rtls.db")
        if not os.path.exists(db_path):
            # Try exec DB name variants
            for cand in (config.DATA_DIR / "holo_rtls.db", config.DATA_DIR / "holo_rtls_exec.db"):
                if cand.exists():
                    db_path = str(cand)
                    break
        shutil.copy2(str(db_path), str(filepath))
        # Optional at-rest encryption (Fernet) when BACKUP_ENCRYPT_KEY is set
        enc_key = os.getenv("BACKUP_ENCRYPT_KEY", "").strip()
        if enc_key:
            try:
                import base64, hashlib
                from cryptography.fernet import Fernet
                key = base64.urlsafe_b64encode(hashlib.sha256(enc_key.encode()).digest())
                f = Fernet(key)
                raw = Path(filepath).read_bytes()
                enc_path = Path(str(filepath) + ".enc")
                enc_path.write_bytes(f.encrypt(raw))
                Path(filepath).unlink(missing_ok=True)
                filename = enc_path.name
                filepath = enc_path
                job.filename = filename
                job.notes = (job.notes or "") + " encrypted=fernet"
            except ImportError:
                pass  # cryptography not installed — leave plaintext
            except Exception as e:
                logger = __import__("logging").getLogger(__name__)
                logger.warning("Backup encryption skipped: %s", e)
        # Retention
        retention = int(getattr(config, "BACKUP_RETENTION_COUNT", 10) or 10)
        jobs = BackupJob.query.filter_by(status="done").order_by(BackupJob.created_at.desc()).all()
        for old in jobs[retention:]:
            old_path = config.BACKUP_DIR / old.filename
            if old_path.exists():
                try:
                    old_path.unlink()
                except Exception:
                    pass
            db.session.delete(old)
        size = os.path.getsize(filepath)
        job.size_bytes = size
        job.status = "done"
        job.completed_at = datetime.now(timezone.utc)
        # Optional offsite push when BACKUP_REMOTE_URL is set
        remote = os.getenv("BACKUP_REMOTE_URL", "").strip()
        if remote and trigger != "pre_restore":
            try:
                import requests
                with open(filepath, "rb") as fh:
                    r = requests.post(
                        remote,
                        files={"file": (filename, fh, "application/octet-stream")},
                        timeout=60,
                        headers={"X-HOLO-Backup": "1"},
                    )
                note = f" remote_push={r.status_code}"
                job.notes = ((job.notes or "") + note).strip()
            except Exception as e:
                job.notes = ((job.notes or "") + f" remote_push_error={str(e)[:120]}").strip()
        db.session.commit()
        return job
    except Exception as e:
        job.status = "failed"
        job.notes = str(e)[:500]
        db.session.commit()
        raise


@backup_bp.route("/trigger", methods=["POST"])
@jwt_required()
@require_permission(Permission.TRIGGER_BACKUP)
def trigger_backup():
    """
    === A
    tags:
      - Backup
    summary: Trigger a manual backup
    description: Creates a new database backup by copying the SQLite database file. Requires TRIGGER_BACKUP permission.
    security:
      - Bearer: []
    responses:
      200:
        description: Backup completed successfully
        schema:
          type: object
          properties:
            job: { type: object }
      500:
        description: Backup failed
        schema:
          type: object
          properties:
            error: { type: string }
            job: { type: object }
    ===
    """
    user_id = int(get_jwt_identity())
    try:
        job = _create_backup_file(trigger="manual", user_id=user_id)
        return jsonify({"job": job.to_dict()}), 200
    except Exception as e:
        job = BackupJob.query.order_by(BackupJob.id.desc()).first()
        return jsonify({"error": str(e), "job": job.to_dict() if job else None}), 500


# Add encryption status to schedule info
@backup_bp.route("/schedule", methods=["GET"])
@jwt_required()
@require_permission(Permission.TRIGGER_BACKUP)
def backup_schedule_info():
    enc = bool(os.getenv("BACKUP_ENCRYPT_KEY", "").strip())
    remote = os.getenv("BACKUP_REMOTE_URL", "").strip()
    return jsonify({
        "enabled": True,
        "cron": "30 2 * * *",
        "description": "Daily automated backup at 02:30 UTC",
        "retention": int(getattr(config, "BACKUP_RETENTION_COUNT", 10) or 10),
        "encryption_enabled": enc,
        "encryption": "fernet" if enc else None,
        "remote_configured": bool(remote),
        "remote_label": (remote.split("://")[0] + "://…") if remote else None,
        "remote_note": "After local backup, POST multipart to BACKUP_REMOTE_URL when set",
    })


@backup_bp.route("/schedule", methods=["PUT", "PATCH"])
@jwt_required()
@require_permission(Permission.TRIGGER_BACKUP)
def update_backup_schedule():
    """Update retention count (schedule time remains daily 02:30 UTC for now)."""
    body = request.get_json() or {}
    if "retention" in body:
        try:
            ret = max(1, min(100, int(body["retention"])))
        except (TypeError, ValueError):
            return jsonify({"error": "retention must be an integer 1–100"}), 400
        # Persist via Setting table when available
        try:
            from backend.models import Setting
            row = Setting.query.filter_by(key="backup_retention_count").first()
            if not row:
                row = Setting(key="backup_retention_count", value=str(ret), value_type="int",
                              label="Backup retention count", scope=1)
                db.session.add(row)
            else:
                row.value = str(ret)
            db.session.commit()
            config.BACKUP_RETENTION_COUNT = ret
        except Exception:
            config.BACKUP_RETENTION_COUNT = ret
    return backup_schedule_info()


@backup_bp.route("/<int:job_id>/download", methods=["GET"])
@jwt_required()
@require_permission(Permission.TRIGGER_BACKUP)
def download_backup(job_id):
    """
    === A
    tags:
      - Backup
    summary: Download a backup file
    description: Downloads a specific backup file by job ID. Requires TRIGGER_BACKUP permission.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: job_id
        required: true
        schema:
          type: integer
        description: Backup job ID
    responses:
      200:
        description: SQLite database file download
        content:
          application/x-sqlite3:
            schema:
              type: string
              format: binary
      404:
        description: Backup file not found
    ===
    """
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
    """
    === A
    tags:
      - Backup
    summary: Restore from a backup
    description: Restores the database from a specific backup file. Requires RESTORE_BACKUP permission and confirmation.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: job_id
        required: true
        schema:
          type: integer
        description: Backup job ID
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - confirm
          properties:
            confirm:
              type: boolean
              description: Must be true to proceed with restore
    responses:
      200:
        description: Restore completed
        schema:
          type: object
          properties:
            message: { type: string }
      400:
        description: Confirmation required or backup not found
      404:
        description: Backup file not found
    ===
    """
    job = BackupJob.query.get_or_404(job_id)
    filepath = config.BACKUP_DIR / job.filename
    if not filepath.exists():
        return jsonify({"error": "Backup file not found"}), 404
    body = request.get_json() or {}
    if not body.get("confirm"):
        return jsonify({"error": "Set confirm=true to restore from backup"}), 400

    # Resolve live DB path (same logic as backup create)
    db_uri = config.SQLALCHEMY_DATABASE_URI or ""
    if not db_uri.startswith("sqlite"):
        return jsonify({"error": "File restore is SQLite-only. Use pg_restore for Postgres."}), 400
    db_path = Path(db_uri.replace("sqlite:///", ""))
    if not db_path.is_absolute():
        db_path = config.DATA_DIR / "holo_rtls.db"

    # Pre-restore safety snapshot
    safety = None
    try:
        safety = _create_backup_file(trigger="pre_restore", user_id=int(get_jwt_identity()))
    except Exception as e:
        return jsonify({"error": f"Could not create safety snapshot before restore: {e}"}), 500

    # Decrypt Fernet backups when needed
    src = filepath
    tmp_dec = None
    if str(filepath).endswith(".enc"):
        enc_key = os.getenv("BACKUP_ENCRYPT_KEY", "").strip()
        if not enc_key:
            return jsonify({"error": "BACKUP_ENCRYPT_KEY required to restore encrypted backup"}), 400
        try:
            import base64, hashlib, tempfile
            from cryptography.fernet import Fernet
            key = base64.urlsafe_b64encode(hashlib.sha256(enc_key.encode()).digest())
            raw = Fernet(key).decrypt(Path(filepath).read_bytes())
            fd, tmp_name = tempfile.mkstemp(suffix=".db", prefix="holo_restore_")
            os.close(fd)
            tmp_dec = Path(tmp_name)
            tmp_dec.write_bytes(raw)
            src = tmp_dec
        except ImportError:
            return jsonify({"error": "cryptography package required to restore encrypted backups"}), 500
        except Exception as e:
            return jsonify({"error": f"Decrypt failed: {e}"}), 400

    try:
        shutil.copy2(str(src), str(db_path))
    finally:
        if tmp_dec and tmp_dec.exists():
            try:
                tmp_dec.unlink()
            except Exception:
                pass

    return jsonify({
        "message": f"Restored from {job.filename} — restart required",
        "safety_backup": safety.to_dict() if safety else None,
        "encrypted": str(filepath).endswith(".enc"),
    })
