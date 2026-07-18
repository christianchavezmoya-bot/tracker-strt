#!/usr/bin/env python3
"""
HOLO-RTLS — Production Entry Point
Run with: python run.py
Or for production: gunicorn -c gunicorn.conf.py run:app
"""
from backend.app import create_app
from backend.extensions import db

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        # Ensure uploads/backup dirs exist
        from backend import config
        config.UPLOAD_DIR.mkdir(exist_ok=True)
        config.BACKUP_DIR.mkdir(exist_ok=True)
        # Create initial admin if no users exist
        from backend.models import User, UserRole
        if User.query.count() == 0:
            admin = User(
                email="admin@holo-rtls.local",
                username="admin",
                display_name="System Administrator",
                role=UserRole.ADMIN,
            )
            admin.set_password("ChangeMe123!")   # Force change on first login
            db.session.add(admin)
            db.session.commit()
            print("✅ Default admin created: admin@holo-rtls.local / ChangeMe123!")

    app.run(
        host="0.0.0.0",
        port=8080,
        debug=app.config.get("DEBUG", False),
    )
