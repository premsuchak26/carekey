"""Tests for unambiguous passcodes, input normalization, email validation, and timezone support."""

import pytest

from app.config import Settings
from app.models import Elder, Member, MemberRole
from app.repositories import RepositoryContainer
from app.services.auth import AuthService


@pytest.fixture
def repos() -> RepositoryContainer:
    c = RepositoryContainer(Settings(repository_backend="memory"))
    c.clear()
    return c


@pytest.fixture
def auth_service(repos: RepositoryContainer) -> AuthService:
    return AuthService(repositories=repos, settings=Settings())


def test_unambiguous_alphabet(auth_service: AuthService):
    """Verify alphabet contains no 0, O, 1, I, L."""
    forbidden = {"0", "O", "1", "I", "L"}
    for ch in auth_service.CHARSET:
        assert ch not in forbidden, f"Forbidden character {ch} found in CHARSET"

    for _ in range(50):
        code = auth_service.generate_passcode()
        assert len(code) == 12
        assert not any(c in forbidden for c in code)

        circle_code = auth_service.generate_circle_code()
        assert not any(c in forbidden for c in circle_code.replace("CARE-", ""))


@pytest.mark.asyncio
async def test_login_normalization_spaces_hyphens_lowercase(auth_service: AuthService):
    """Verify login trims, uppercases, and ignores hyphens and spaces in credentials."""
    circle, _elder, raw_passcode = await auth_service.create_circle(
        elder_name="Amma",
        elder_email="amma@example.com",
        timezone="Asia/Kolkata",
    )

    # raw_passcode is e.g. "ABCDEF234567"
    # User types lowercase, spaces, hyphens
    spaced_passcode = (
        f" {raw_passcode[:4].lower()} - {raw_passcode[4:8].lower()} - {raw_passcode[8:]} "
    )
    # circle.circle_code is e.g. "CARE-XXXX"
    sloppy_circle_code = f" care - {circle.circle_code.replace('CARE-', '').lower()} "

    logged_circle, logged_member = await auth_service.login(
        circle_code=sloppy_circle_code,
        passcode=spaced_passcode,
    )
    assert logged_circle.id == circle.id
    assert logged_member.role == MemberRole.ELDER


def test_email_validation_elder_and_member():
    """Verify invalid emails raise ValueError, valid emails are accepted."""
    with pytest.raises(ValueError):
        Elder(name="Test", email="not-an-email")

    with pytest.raises(ValueError):
        Member(
            circle_id="c1",
            name="Caregiver",
            email="bad@@email.com",
            role=MemberRole.HELPER,
            key_hash="hash",
            salt="salt",
        )

    elder = Elder(name="Valid", email="Valid.User@Domain.Com", timezone="Asia/Kolkata")
    assert elder.email == "valid.user@domain.com"
    assert elder.timezone == "Asia/Kolkata"


def test_timezone_validation():
    """Verify invalid timezone raises ValueError."""
    with pytest.raises(ValueError):
        Elder(name="Test", email="elder@test.com", timezone="Invalid/Timezone_Name")

    elder = Elder(name="Test", email="elder@test.com", timezone="UTC")
    assert elder.timezone == "UTC"
