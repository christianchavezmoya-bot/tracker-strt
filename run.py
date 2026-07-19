#!/usr/bin/env python3
"""
HOLO-RTLS — Production Entry Point
Run with: python run.py
Or for production: gunicorn -c gunicorn.conf.py run:app
"""
from backend.app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8080,
        debug=app.config.get("DEBUG", False),
    )
