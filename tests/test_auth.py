"""Tests for authentication, scrypt hashing, lockouts, expiry, and revocation."""

from datetime import datetime

import pytest

from app.config import Settings
from app.models import MemberRole
from app.repositories import RepositoryContainer
from app.services.auth import AuthError, AuthService


@pytest.mark.asyncio
async def test_scrypt_hashing_and_verification() -> None:
    """Verify that passcode is hashed with scrypt and verified in constant time."""
    passcode = "TESTKEY12345"
    salt, key_hash = AuthService.hash_passcode(passcode)

    assert salt is not None
    assert key_hash is not None
    assert len(salt) == 32  # 16 bytes in hex

    # Verify matching passcode
    assert AuthService.verify_passcode(passcode, salt, key_hash) is True

    # Verify wrong passcode
    assert AuthService.verify_passcode("WRONGKEY9999", salt, key_hash) is False

    # Different salts produce different hashes
    _, hash2 = AuthService.hash_passcode(passcode)
    assert key_hash != hash2


@pytest.mark.asyncio
async def test_circle_creation_and_owner_login(
    test_repos: RepositoryContainer, test_settings: Settings
) -> None:
    """Verify circle creation gives owner passcode and allows login."""
    auth = AuthService(repositories=test_repos, settings=test_settings)

    circle, _elder, owner_passcode = await auth.create_circle(elder_name="Margaret")

    assert circle.circle_code.startswith("CARE-")
    assert len(owner_passcode) == 12

    # Successful login
    logged_circle, member = await auth.login(circle.circle_code, owner_passcode)
    assert logged_circle.id == circle.id
    assert member.role == MemberRole.ELDER
    assert member.failed_attempts == 0


@pytest.mark.asyncio
async def test_generic_error_on_invalid_credentials(
    test_repos: RepositoryContainer, test_settings: Settings
) -> None:
    """Verify generic error message is returned for invalid credentials."""
    auth = AuthService(repositories=test_repos, settings=test_settings)
    circle, _, _ = await auth.create_circle(elder_name="Thomas")

    # Wrong passcode
    with pytest.raises(AuthError) as exc_info:
        await auth.login(circle.circle_code, "INVALIDPASS1")
    assert exc_info.value.message == "Invalid circle code or passcode."

    # Unknown circle code
    with pytest.raises(AuthError) as exc_info2:
        await auth.login("CARE-ZZZZ", "ANYPASSCODE1")
    assert exc_info2.value.message == "Invalid circle code or passcode."


@pytest.mark.asyncio
async def test_lockout_after_five_failed_attempts(
    test_repos: RepositoryContainer, test_settings: Settings
) -> None:
    """Verify that 5 failed login attempts trigger a 15-minute lockout."""
    auth = AuthService(repositories=test_repos, settings=test_settings)
    circle, _, correct_passcode = await auth.create_circle(elder_name="Eleanor")

    # 4 failed attempts should fail with standard error
    for _ in range(4):
        with pytest.raises(AuthError) as exc:
            await auth.login(circle.circle_code, "WRONGCODE111")
        assert exc.value.message == "Invalid circle code or passcode."

    # 5th failed attempt triggers lockout
    with pytest.raises(AuthError):
        await auth.login(circle.circle_code, "WRONGCODE111")

    # Subsequent attempt (even with correct passcode) must be rejected due to lockout
    with pytest.raises(AuthError) as exc_locked:
        await auth.login(circle.circle_code, correct_passcode)
    assert "locked" in exc_locked.value.message.lower()


@pytest.mark.asyncio
async def test_expired_key_denied(
    test_repos: RepositoryContainer, test_settings: Settings
) -> None:
    """Verify expired member key cannot log in."""
    auth = AuthService(repositories=test_repos, settings=test_settings)
    circle, _, _ = await auth.create_circle(elder_name="Arthur")

    # Issue member key with negative validity (already expired)
    member, raw_key = await auth.issue_member_key(
        circle_id=circle.id,
        name="Nurse Joy",
        role=MemberRole.HELPER,
        validity_days=-1,
    )

    assert member.expires_at is not None
    assert member.expires_at < datetime.now()

    with pytest.raises(AuthError) as exc:
        await auth.login(circle.circle_code, raw_key)
    assert exc.value.message == "Invalid circle code or passcode."


@pytest.mark.asyncio
async def test_revoked_key_denied(
    test_repos: RepositoryContainer, test_settings: Settings
) -> None:
    """Verify revoked member key is instantly denied login."""
    auth = AuthService(repositories=test_repos, settings=test_settings)
    circle, _, _ = await auth.create_circle(elder_name="Clara")

    member, raw_key = await auth.issue_member_key(
        circle_id=circle.id,
        name="Caretaker Sam",
        role=MemberRole.MANAGER,
        validity_days=30,
    )

    # Valid before revocation
    _c, m = await auth.login(circle.circle_code, raw_key)
    assert m.id == member.id

    # Revoke key
    revoked = await auth.revoke_member_key(circle.id, member.id)
    assert revoked is True

    # Denied after revocation
    with pytest.raises(AuthError) as exc:
        await auth.login(circle.circle_code, raw_key)
    assert exc.value.message == "Invalid circle code or passcode."


@pytest.mark.asyncio
async def test_ip_rate_limiting(
    test_repos: RepositoryContainer, test_settings: Settings
) -> None:
    """Verify that exceeding IP rate limit blocks further attempts."""
    auth = AuthService(repositories=test_repos, settings=test_settings)
    ip = "192.168.1.50"

    # Fill rate limit threshold
    for _ in range(AuthService.IP_RATE_LIMIT_MAX_ATTEMPTS):
        auth.record_ip_failure(ip)

    with pytest.raises(AuthError) as exc:
        await auth.login("CARE-NONE", "SOMEKEY12345", client_ip=ip)
    assert "too many" in exc.value.message.lower()
