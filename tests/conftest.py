"""
HOLO-RTLS — Test Configuration (pytest fixtures)
"""
import os, sys
import pytest

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-testing-only-32chars")
os.environ.setdefault("FLASK_DEBUG", "1")


@pytest.fixture(scope="function")
def app():
    from backend.app import create_app
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
    app = create_app(test_config)
    with app.app_context():
        from backend.extensions import db
        from backend.services.notification_service import init_notification_service
        init_notification_service(db.session, app)
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def app_context(app):
    with app.app_context():
        yield


@pytest.fixture
def db_session(app):
    from backend.extensions import db
    with app.app_context():
        yield db.session
        db.session.rollback()


@pytest.fixture
def sample_user(app):
    from backend.extensions import db
    from backend.models import User, UserRole
    with app.app_context():
        user = User(
            email="testuser@example.com",
            username="testuser",
            display_name="Test User",
            role=UserRole.OPERATOR,
        )
        user.set_password("TestPass123!")
        db.session.add(user)
        db.session.commit()
        yield user


@pytest.fixture
def admin_user(app):
    from backend.extensions import db
    from backend.models import User, UserRole
    with app.app_context():
        user = User(
            email="admin@example.com",
            username="admin",
            display_name="Admin User",
            role=UserRole.ADMIN,
        )
        user.set_password("AdminPass123!")
        db.session.add(user)
        db.session.commit()
        yield user


@pytest.fixture
def auth_headers(client, sample_user):
    """Get JWT access token for sample_user."""
    resp = client.post("/api/auth/login", json={
        "email_or_username": "testuser@example.com",
        "password": "TestPass123!",
    })
    data = resp.get_json()
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.fixture
def admin_headers(client, admin_user):
    """Get JWT access token for admin_user."""
    resp = client.post("/api/auth/login", json={
        "email_or_username": "admin@example.com",
        "password": "AdminPass123!",
    })
    data = resp.get_json()
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.fixture
def viewer_user(app):
    """Create a VIEWER-role user."""
    from backend.extensions import db
    from backend.models import User, UserRole
    with app.app_context():
        user = User(
            email="viewer@example.com",
            username="viewer",
            display_name="Viewer User",
            role=UserRole.VIEWER,
        )
        user.set_password("ViewerPass123!")
        db.session.add(user)
        db.session.commit()
        yield user


@pytest.fixture
def viewer_headers(client, viewer_user):
    """Get JWT access token for viewer_user."""
    resp = client.post("/api/auth/login", json={
        "email_or_username": "viewer@example.com",
        "password": "ViewerPass123!",
    })
    data = resp.get_json()
    return {"Authorization": f"Bearer {data['access_token']}"}
