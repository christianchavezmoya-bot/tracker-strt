"""
HOLO-RTLS — Authentication Service
Handles register, login, logout, password reset, 2FA.
"""
import pyotp
import qrcode
import io
import base64
from typing import Optional, Tuple
from flask_jwt_extended import create_access_token, create_refresh_token, get_jti
from argon2.exceptions import VerifyMismatchError, InvalidHash

from backend.extensions import db
from backend.models import User, UserRole, AuditLog
from backend.services.rbac_service import RBAC_SERVICE


class AuthService:
    """
    Business logic for authentication.
    Called by auth API routes — keeps routes thin.
    """

    def create_user(
        self,
        email: str,
        password: str,
        username: Optional[str] = None,
        display_name: Optional[str] = None,
        role: int = UserRole.OPERATOR,
        phone: Optional[str] = None,
    ) -> User:
        """Admin create-user helper used by /api/users."""
        email = email.strip().lower()
        username = (username or email.split("@")[0]).strip()
        user, err = self.register(
            email=email,
            username=username,
            password=password,
            role=role,
            display_name=display_name,
        )
        if err:
            raise ValueError(err)
        if phone:
            user.phone = phone.strip()
            db.session.commit()
        return user

    # ── Registration ──────────────────────────────────────────────────────────
    def register(
        self,
        email: str,
        username: str,
        password: str,
        role: int = UserRole.VIEWER,
        display_name: Optional[str] = None,
        created_by_id: Optional[int] = None,
    ) -> Tuple[User, str]:
        """
        Create a new user account.
        Returns (user, error_message).
        """
        # Normalize
        email = email.strip().lower()
        username = username.strip()

        # Check uniqueness
        if User.query.filter_by(email=email).first():
            return None, "Email already registered"
        if User.query.filter_by(username=username).first():
            return None, "Username already taken"

        if len(password) < 8:
            return None, "Password must be at least 8 characters"

        user = User(
            email=email,
            username=username,
            display_name=display_name or username,
            role=role,
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        AuditLog.log(
            action="user.register",
            user_id=user.id,
            entity_type="User",
            entity_id=user.id,
            details=f'{{"email": "{email}", "role": "{UserRole(role).name}"}}',
        )

        return user, None

    # ── Login ─────────────────────────────────────────────────────────────────
    def login(
        self,
        email_or_username: str,
        password: str,
        totp_code: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Tuple[dict, Optional[str]]:
        """
        Authenticate a user.
        Returns ({tokens + user}, error_message).
        """
        # Find user by email or username
        user = (
            User.query.filter_by(email=email_or_username.strip().lower()).first()
            or User.query.filter_by(username=email_or_username.strip()).first()
        )

        if not user:
            return None, "Invalid credentials"

        # Check lockout
        if user.is_locked:
            locked = user.locked_until
            retry_after = None
            if locked:
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                if locked.tzinfo is None:
                    locked = locked.replace(tzinfo=timezone.utc)
                retry_after = max(0, int((locked - now).total_seconds()))
            return None, {
                "error": "Account locked. Try again later.",
                "code": "account_locked",
                "retry_after_seconds": retry_after,
                "locked_until": locked.isoformat() if locked else None,
            }

        if not user.is_active:
            return None, "Account is deactivated. Contact an administrator."

        # Verify password
        try:
            if not user.check_password(password):
                self._handle_failed_login(user, ip_address)
                return None, "Invalid credentials"
        except (VerifyMismatchError, InvalidHash):
            self._handle_failed_login(user, ip_address)
            return None, "Invalid credentials"

        # Check 2FA if enabled
        if user.is_2fa_enabled:
            if not totp_code:
                # Return partial success — tell client to ask for TOTP
                return {"requires_2fa": True, "user_id": user.id}, None
            if not self._verify_totp(user.totp_secret, totp_code):
                self._handle_failed_login(user, ip_address)
                return None, "Invalid 2FA code"

        # Success
        user.record_successful_login()

        access_token = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))

        # Track session for revoke / force-logout
        try:
            from backend.api.sessions import register_session
            register_session(
                user.id,
                get_jti(access_token),
                ip=ip_address,
                ua=None,
            )
        except Exception:
            pass

        AuditLog.log(
            action="user.login",
            user_id=user.id,
            entity_type="User",
            entity_id=user.id,
            ip_address=ip_address,
        )

        return {
            "requires_2fa": False,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user.to_dict(include_email=True),
        }, None
    def _handle_failed_login(self, user: User, ip_address: Optional[str]):
        locked = user.record_failed_login()
        AuditLog.log(
            action="user.login_failed",
            user_id=user.id,
            entity_type="User",
            entity_id=user.id,
            ip_address=ip_address,
            details='{"reason": "invalid_password"}',
        )

    # ── 2FA Setup ──────────────────────────────────────────────────────────────
    def setup_2fa(self, user_id: int) -> Tuple[Optional[str], Optional[str]]:
        """
        Generate a new TOTP secret and QR code for a user.
        Returns (qr_code_base64, secret) or (None, error).
        """
        user = User.query.get(user_id)
        if not user:
            return None, "User not found"

        if user.is_2fa_enabled:
            return None, "2FA is already enabled"

        # Generate a random base32 secret (16 chars = 80 bits, standard for TOTP)
        secret = pyotp.random_base32()
        user.totp_secret = secret
        db.session.commit()

        # Generate provisioning URI (for Google Authenticator, Authy, etc.)
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name="HOLO-RTLS",
        )

        # Generate QR code as base64 PNG
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(totp_uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        qr_b64 = base64.b64encode(buf.read()).decode("utf-8")

        AuditLog.log(
            action="user.2fa_setup_initiated",
            user_id=user_id,
            entity_type="User",
            entity_id=user_id,
        )

        return qr_b64, None

    def confirm_2fa(self, user_id: int, totp_code: str) -> Tuple[bool, Optional[str]]:
        """
        Confirm 2FA setup after user verifies a code.
        Returns (success, error_message).
        """
        user = User.query.get(user_id)
        if not user:
            return False, "User not found"

        if not user.totp_secret:
            return False, "No 2FA secret set up"

        if not self._verify_totp(user.totp_secret, totp_code):
            return False, "Invalid verification code"

        user.is_2fa_enabled = True
        db.session.commit()

        AuditLog.log(
            action="user.2fa_enabled",
            user_id=user_id,
            entity_type="User",
            entity_id=user_id,
        )

        return True, None

    def disable_2fa(self, user_id: int, password: str, totp_code: str) -> Tuple[bool, Optional[str]]:
        """
        Disable 2FA (requires password + current TOTP code).
        """
        user = User.query.get(user_id)
        if not user:
            return False, "User not found"

        if not user.check_password(password):
            return False, "Invalid password"

        if not self._verify_totp(user.totp_secret, totp_code):
            return False, "Invalid 2FA code"

        user.is_2fa_enabled = False
        user.totp_secret = None
        db.session.commit()

        AuditLog.log(
            action="user.2fa_disabled",
            user_id=user_id,
            entity_type="User",
            entity_id=user_id,
        )

        return True, None

    def _verify_totp(self, secret: str, code: str) -> bool:
        """Verify a TOTP code against a secret."""
        try:
            totp = pyotp.TOTP(secret)
            return totp.verify(code, valid_window=1)   # ±30s window
        except Exception:
            return False

    # ── Password Reset ────────────────────────────────────────────────────────
    def request_password_reset(self, email: str, ip_address: Optional[str] = None) -> bool:
        """
        Initiate password reset for an email.
        Returns True always (don't reveal whether email exists).
        In DEBUG / mail-suppressed mode the reset token is audited for operators.
        """
        import time
        import jwt as pyjwt
        from backend.config import JWT_SECRET_KEY, PASSWORD_RESET_TOKEN_EXPIRES, DEBUG, FLASK_MAIL_SUPPRESS_SEND

        user = User.query.filter_by(email=email.strip().lower()).first()
        if user:
            token = pyjwt.encode(
                {
                    "sub": str(user.id),
                    "type": "password_reset",
                    "exp": int(time.time()) + int(PASSWORD_RESET_TOKEN_EXPIRES),
                },
                JWT_SECRET_KEY,
                algorithm="HS256",
            )
            if isinstance(token, bytes):
                token = token.decode("utf-8")

            # Attempt email delivery
            mailed = False
            try:
                from backend.services.notification_service import get_notification_service
                notif = get_notification_service()
                if notif:
                    mailed = bool(notif.send_email(
                        to=user.email,
                        subject="HOLO-RTLS password reset",
                        body=f"Use this token on the reset form (valid ~1 hour):\n\n{token}\n\nOr open /login and paste it into Reset Password.",
                    ))
            except Exception:
                mailed = False

            AuditLog.log(
                action="user.password_reset_requested",
                user_id=user.id,
                entity_type="User",
                entity_id=user.id,
                ip_address=ip_address,
                details=f'{{"mailed": {str(mailed).lower()}, "debug_token": "{token if (DEBUG or FLASK_MAIL_SUPPRESS_SEND) else ""}"}}',
            )
            # Stash last debug token on service for API to optionally return in DEBUG
            self._last_reset_token = token if (DEBUG or FLASK_MAIL_SUPPRESS_SEND) else None
        return True

    def reset_password(self, token: str, new_password: str) -> Tuple[bool, Optional[str]]:
        """
        Reset password using a signed token.
        Returns (success, error_message).
        """
        from backend.config import JWT_SECRET_KEY
        import jwt as pyjwt, time

        try:
            payload = pyjwt.decode(
                token,
                JWT_SECRET_KEY,
                algorithms=["HS256"],
            )
            user_id = int(payload.get("sub"))
            if payload.get("type") != "password_reset":
                return False, "Invalid token"
            expires = payload.get("exp", 0)
            if time.time() > expires:
                return False, "Token expired"
        except Exception:
            return False, "Invalid token"

        user = User.query.get(user_id)
        if not user:
            return False, "User not found"

        if len(new_password) < 8:
            return False, "Password must be at least 8 characters"

        user.set_password(new_password)
        db.session.commit()

        AuditLog.log(
            action="user.password_reset_complete",
            user_id=user_id,
            entity_type="User",
            entity_id=user_id,
        )

        return True, None

    # ── Session / Logout ──────────────────────────────────────────────────────
    def logout(self, user_id: int, ip_address: Optional[str] = None):
        """Log a user out (audit only — JWT revocation handled client-side)."""
        AuditLog.log(
            action="user.logout",
            user_id=user_id,
            entity_type="User",
            entity_id=user_id,
            ip_address=ip_address,
        )

    # ── Token Refresh ─────────────────────────────────────────────────────────
    def refresh_access_token(self, user_id: str) -> str:
        """Create a new access token from a refresh token."""
        return create_access_token(identity=user_id)


# ── Singleton ────────────────────────────────────────────────────────────────
AUTH_SERVICE = AuthService()
