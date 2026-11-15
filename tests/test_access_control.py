"""Tests for role enforcement, cross-circle access isolation, and CSRF protection."""

from datetime import datetime

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.config import Settings
from app.models import MemberRole
from app.repositories import RepositoryContainer
from app.services.auth import AuthService
from app.services.medication import MedicationService
from app.services.session import SessionManager


@pytest.mark.asyncio
async def test_role_hierarchy_permissions(
    test_repos: RepositoryContainer, test_settings: Settings
) -> None:
    """Verify that role level accurately determines capability."""
    assert MemberRole.VIEWER.level < MemberRole.HELPER.level
    assert MemberRole.HELPER.level < MemberRole.MANAGER.level
    assert MemberRole.MANAGER.level < MemberRole.ELDER.level


def test_csrf_token_required_on_post(
    client: TestClient, test_repos: RepositoryContainer, test_settings: Settings
) -> None:
    """Verify state-changing POST requests require a valid CSRF token."""
    session_mgr = SessionManager(settings=test_settings)
    auth = AuthService(repositories=test_repos, settings=test_settings)

    # Setup circle and elder
    import asyncio

    circle, _, _ = asyncio.run(auth.create_circle(elder_name="Robert"))
    members = asyncio.run(test_repos.members.find(lambda m: m.circle_id == circle.id))
    owner = members[0]

    # Set valid session cookie
    token = session_mgr.create_session_token(
        circle_id=circle.id,
        member_id=owner.id,
        role=owner.role.value,
        member_name=owner.name,
    )
    client.cookies.set(session_mgr.COOKIE_NAME, token)

    # POST without CSRF token must be 403 Forbidden
    response_no_csrf = client.post(
        "/medications/add",
        data={"name": "Aspirin", "dosage": "81mg"},
    )
    assert response_no_csrf.status_code == status.HTTP_403_FORBIDDEN

    # POST with invalid CSRF token must be 403 Forbidden
    response_bad_csrf = client.post(
        "/medications/add",
        data={"name": "Aspirin", "dosage": "81mg", "csrf_token": "invalid-token-123"},
    )
    assert response_bad_csrf.status_code == status.HTTP_403_FORBIDDEN

    # POST with valid CSRF token succeeds
    valid_csrf = session_mgr.generate_csrf_token(owner.id)
    response_valid = client.post(
        "/medications/add",
        data={
            "name": "Aspirin",
            "dosage": "81mg",
            "csrf_token": valid_csrf,
        },
        follow_redirects=False,
    )
    assert response_valid.status_code == status.HTTP_303_SEE_OTHER


def test_viewer_cannot_add_medication_or_log_dose(
    client: TestClient, test_repos: RepositoryContainer, test_settings: Settings
) -> None:
    """Verify VIEWER role is strictly read-only."""
    import asyncio

    session_mgr = SessionManager(settings=test_settings)
    auth = AuthService(repositories=test_repos, settings=test_settings)

    circle, _, _ = asyncio.run(auth.create_circle(elder_name="Florence"))
    viewer_member, _ = asyncio.run(
        auth.issue_member_key(circle.id, name="Viewer Bob", role=MemberRole.VIEWER)
    )

    token = session_mgr.create_session_token(
        circle_id=circle.id,
        member_id=viewer_member.id,
        role=viewer_member.role.value,
    )
    client.cookies.set(session_mgr.COOKIE_NAME, token)
    csrf = session_mgr.generate_csrf_token(viewer_member.id)

    # Attempting to add medication as VIEWER
    res_add = client.post(
        "/medications/add",
        data={"name": "Atorvastatin", "dosage": "20mg", "csrf_token": csrf},
    )
    assert res_add.status_code == status.HTTP_403_FORBIDDEN

    # Attempting to log dose as VIEWER
    res_dose = client.post(
        "/today/dose/take",
        data={"medication_id": "dummy", "time_str": "08:00", "csrf_token": csrf},
    )
    assert res_dose.status_code == status.HTTP_403_FORBIDDEN


def test_helper_cannot_add_medication_or_keys(
    client: TestClient, test_repos: RepositoryContainer, test_settings: Settings
) -> None:
    """Verify HELPER can log doses, but cannot create meds or issue keys."""
    import asyncio

    session_mgr = SessionManager(settings=test_settings)
    auth = AuthService(repositories=test_repos, settings=test_settings)

    circle, _, _ = asyncio.run(auth.create_circle(elder_name="Walter"))
    helper_member, _ = asyncio.run(
        auth.issue_member_key(circle.id, name="Helper Alice", role=MemberRole.HELPER)
    )

    token = session_mgr.create_session_token(
        circle_id=circle.id,
        member_id=helper_member.id,
        role=helper_member.role.value,
    )
    client.cookies.set(session_mgr.COOKIE_NAME, token)
    csrf = session_mgr.generate_csrf_token(helper_member.id)

    # HELPER attempting to access Key management
    res_keys = client.get("/keys")
    assert res_keys.status_code == status.HTTP_403_FORBIDDEN

    # HELPER attempting to add medication
    res_add_med = client.post(
        "/medications/add",
        data={"name": "Omeprazole", "dosage": "20mg", "csrf_token": csrf},
    )
    assert res_add_med.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_cross_circle_access_denied(
    test_repos: RepositoryContainer, test_settings: Settings
) -> None:
    """Verify member of Circle A cannot view or modify Circle B's medications."""
    auth = AuthService(repositories=test_repos, settings=test_settings)
    med_service = MedicationService(repositories=test_repos)

    # Circle A
    circle_a, _, _ = await auth.create_circle(elder_name="Circle A Elder")
    med_a = await med_service.add_medication(circle_id=circle_a.id, name="Med A", dosage="10mg")

    # Circle B
    circle_b, _, _ = await auth.create_circle(elder_name="Circle B Elder")

    # Member of Circle B attempting to access or delete Med A
    deleted = await med_service.delete_medication(circle_id=circle_b.id, medication_id=med_a.id)
    assert deleted is False  # Must fail cross-circle deletion

    # Med A must still exist in Circle A
    still_exists = await test_repos.medications.get(med_a.id)
    assert still_exists is not None

    # Logging a dose for Med A from Circle B must raise ValueError
    with pytest.raises(ValueError):
        await med_service.log_dose(
            circle_id=circle_b.id,
            medication_id=med_a.id,
            scheduled_time=datetime.now(),
            status="taken",
        )
