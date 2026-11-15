"""Tests for production mode configuration, secret validation, and secure cookies."""

import pytest
from fastapi import Response

from app.config import Settings
from app.main import create_app
from app.services.session import SessionManager


def test_production_mode_refuses_default_secret_key() -> None:
    """Settings must reject default or missing secret_key in production."""
    with pytest.raises(ValueError, match="SECRET_KEY environment variable is required"):
        Settings(
            environment="production",
            secret_key="change-this-in-production-to-a-secure-random-key",
            tick_secret="prod-tick-secret-12345",
        )


def test_production_mode_refuses_default_tick_secret() -> None:
    """Settings must reject default or missing tick_secret in production."""
    with pytest.raises(ValueError, match="TICK_SECRET environment variable is required"):
        Settings(
            environment="production",
            secret_key="prod-secret-key-very-secure-random-value",
            tick_secret="carekey-internal-tick-secret",
        )


def test_production_mode_allows_valid_secrets() -> None:
    """Settings must accept production mode with custom, strong secrets."""
    settings = Settings(
        environment="production",
        secret_key="prod-secret-key-very-secure-random-value",
        tick_secret="prod-tick-secret-very-secure-random-value",
    )
    assert settings.environment == "production"
    assert settings.secret_key == "prod-secret-key-very-secure-random-value"
    assert settings.tick_secret == "prod-tick-secret-very-secure-random-value"

    app = create_app(settings)
    assert app.title == "CareKey"


def test_production_mode_session_cookie_is_secure() -> None:
    """Session cookies set in production mode must have Secure=True."""
    settings = Settings(
        environment="production",
        secret_key="prod-secret-key-very-secure-random-value",
        tick_secret="prod-tick-secret-very-secure-random-value",
        debug=False,
    )
    session_manager = SessionManager(settings=settings)
    response = Response()

    session_manager.set_session_cookie(
        response=response,
        circle_id="circle-123",
        member_id="member-456",
        role="ELDER",
    )

    set_cookie_header = response.headers.get("set-cookie", "")
    assert "Secure" in set_cookie_header
    assert "HttpOnly" in set_cookie_header
    assert "samesite=lax" in set_cookie_header.lower()


def test_development_mode_session_cookie_not_secure_when_debug() -> None:
    """Session cookies in development mode with debug=True do not require Secure."""
    settings = Settings(
        environment="development",
        debug=True,
    )
    session_manager = SessionManager(settings=settings)
    response = Response()

    session_manager.set_session_cookie(
        response=response,
        circle_id="circle-123",
        member_id="member-456",
        role="ELDER",
    )

    set_cookie_header = response.headers.get("set-cookie", "")
    assert "Secure" not in set_cookie_header
    assert "HttpOnly" in set_cookie_header
