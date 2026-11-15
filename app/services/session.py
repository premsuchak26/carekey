"""Session and CSRF security management."""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import Request, Response

from app.config import Settings


class SessionManager:
    """Cryptographic session and CSRF token manager."""

    COOKIE_NAME = "carekey_session"
    DEFAULT_MAX_AGE = 3600  # 1 hour short lifetime

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.secret_key = settings.secret_key.encode("utf-8")

    def _sign(self, data: bytes) -> str:
        """Create HMAC-SHA256 signature for binary data."""
        signature = hmac.new(self.secret_key, data, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(signature).decode("utf-8")

    def create_session_token(
        self,
        circle_id: str,
        member_id: str,
        role: str,
        elder_name: str = "",
        member_name: str = "",
        max_age: int = DEFAULT_MAX_AGE,
    ) -> str:
        """Create signed session token containing claims."""
        payload: dict[str, Any] = {
            "circle_id": circle_id,
            "member_id": member_id,
            "role": role,
            "elder_name": elder_name,
            "member_name": member_name,
            "exp": int(time.time()) + max_age,
        }
        encoded_payload = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode(
            "utf-8"
        )
        sig = self._sign(encoded_payload.encode("utf-8"))
        return f"{encoded_payload}.{sig}"

    def verify_session_token(self, token: str) -> dict[str, Any] | None:
        """Verify signature and expiration of session token."""
        try:
            clean_token = token.strip().strip('"')
            parts = clean_token.split(".")
            if len(parts) != 2:
                return None
            encoded_payload, sig = parts[0], parts[1]
            expected_sig = self._sign(encoded_payload.encode("utf-8"))
            if not hmac.compare_digest(sig, expected_sig):
                return None

            payload_bytes = base64.urlsafe_b64decode(encoded_payload.encode("utf-8"))
            payload: dict[str, Any] = json.loads(payload_bytes.decode("utf-8"))

            if payload.get("exp", 0) < int(time.time()):
                return None

            return payload
        except Exception:
            return None

    def set_session_cookie(
        self,
        response: Response,
        circle_id: str,
        member_id: str,
        role: str,
        elder_name: str = "",
        member_name: str = "",
        max_age: int = DEFAULT_MAX_AGE,
    ) -> str:
        """Set signed HttpOnly SameSite=Lax session cookie."""
        token = self.create_session_token(
            circle_id=circle_id,
            member_id=member_id,
            role=role,
            elder_name=elder_name,
            member_name=member_name,
            max_age=max_age,
        )
        response.set_cookie(
            key=self.COOKIE_NAME,
            value=token,
            max_age=max_age,
            httponly=True,
            samesite="lax",
            secure=not self.settings.debug,  # False for test/localhost dev
            path="/",
        )
        return token

    def clear_session_cookie(self, response: Response) -> None:
        """Clear session cookie on logout."""
        response.delete_cookie(key=self.COOKIE_NAME, path="/")

    def get_session(self, request: Request) -> dict[str, Any] | None:
        """Extract and validate session from request cookie."""
        token = request.cookies.get(self.COOKIE_NAME)
        if not token:
            return None
        return self.verify_session_token(token)

    def generate_csrf_token(self, member_id: str) -> str:
        """Generate a CSRF token bound to member session."""
        raw = f"csrf:{member_id}:{self.settings.secret_key}".encode()
        return hashlib.sha256(raw).hexdigest()

    def validate_csrf_token(self, member_id: str, submitted_token: str | None) -> bool:
        """Validate submitted CSRF token using constant-time comparison."""
        if not submitted_token:
            return False
        expected = self.generate_csrf_token(member_id)
        return hmac.compare_digest(submitted_token, expected)
