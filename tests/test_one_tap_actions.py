"""Tests for one-tap email actions: signed tokens, single-use,
expiration, GET confirmation, and POST execution.
"""

import pytest

from app.config import Settings
from app.models import CareCircle, DoseSchedule, Elder, Medication, Member, MemberRole
from app.repositories import RepositoryContainer
from app.services.action_tokens import ActionTokenManager
from app.services.audit import AuditService
from app.services.email import FakeEmailSender
from app.services.medication import MedicationService


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        app_name="CareKey-Test",
        environment="test",
        debug=True,
        repository_backend="memory",
        secret_key="secret-key-for-signing-action-tokens",
        app_base_url="http://testserver",
    )


@pytest.fixture
def repos(test_settings: Settings) -> RepositoryContainer:
    c = RepositoryContainer(test_settings)
    c.clear()
    return c


@pytest.fixture
def token_manager(test_settings: Settings, repos: RepositoryContainer) -> ActionTokenManager:
    return ActionTokenManager(settings=test_settings, repos=repos)


@pytest.fixture
async def setup_circle(repos: RepositoryContainer) -> tuple[CareCircle, Elder, Medication, Member]:
    elder = Elder(name="Grandma Joy", email="joy@carekey.local", timezone="Asia/Kolkata")
    await repos.elders.save(elder.id, elder)

    circle = CareCircle(circle_code="CARE-JOY1", elder_id=elder.id, name="Joy Circle")
    await repos.circles.save(circle.id, circle)

    from uuid import uuid4

    med_id = str(uuid4())
    med = Medication(
        id=med_id,
        circle_id=circle.id,
        name="Lisinopril",
        dosage="10mg",
        schedule=DoseSchedule(medication_id=med_id, times_of_day=["09:00"]),
    )
    await repos.medications.save(med.id, med)

    caregiver = Member(
        circle_id=circle.id,
        name="Nurse Pat",
        email="pat@carekey.local",
        role=MemberRole.MANAGER,
        key_hash="hash",
        salt="salt",
    )
    await repos.members.save(caregiver.id, caregiver)

    return circle, elder, med, caregiver


@pytest.mark.asyncio
async def test_generate_and_verify_token(
    token_manager: ActionTokenManager,
    setup_circle: tuple[CareCircle, Elder, Medication, Member],
):
    circle, _elder, med, _caregiver = setup_circle

    token = token_manager.create_action_token(
        circle_id=circle.id,
        medication_id=med.id,
        scheduled_time="09:00",
        action="took_it",
        expiry_hours=24,
    )
    assert isinstance(token, str)

    payload = await token_manager.verify_token(token)
    assert payload is not None
    assert payload.circle_id == circle.id
    assert payload.medication_id == med.id
    assert payload.scheduled_time == "09:00"
    assert payload.action == "took_it"


@pytest.mark.asyncio
async def test_token_tampering_rejected(
    token_manager: ActionTokenManager,
    setup_circle: tuple[CareCircle, Elder, Medication, Member],
):
    circle, _elder, med, _caregiver = setup_circle

    token = token_manager.create_action_token(
        circle_id=circle.id,
        medication_id=med.id,
        scheduled_time="09:00",
        action="took_it",
    )

    # Tamper with token string
    tampered = token[:-4] + ("AAAA" if token[-4:] != "AAAA" else "BBBB")
    payload = await token_manager.verify_token(tampered)
    assert payload is None


@pytest.mark.asyncio
async def test_token_expiration_rejected(
    token_manager: ActionTokenManager,
    setup_circle: tuple[CareCircle, Elder, Medication, Member],
):
    circle, _elder, med, _caregiver = setup_circle

    # Token expired 1 hour ago
    token = token_manager.create_action_token(
        circle_id=circle.id,
        medication_id=med.id,
        scheduled_time="09:00",
        action="snooze",
        expiry_hours=-1,
    )

    payload = await token_manager.verify_token(token)
    assert payload is None


@pytest.mark.asyncio
async def test_token_single_use_enforcement(
    token_manager: ActionTokenManager,
    repos: RepositoryContainer,
    setup_circle: tuple[CareCircle, Elder, Medication, Member],
):
    circle, _elder, med, _caregiver = setup_circle

    token = token_manager.create_action_token(
        circle_id=circle.id,
        medication_id=med.id,
        scheduled_time="09:00",
        action="took_it",
    )

    payload = await token_manager.verify_token(token)
    assert payload is not None

    # Consume the token
    await token_manager.consume_token(payload.token_id, payload.action)

    # Second verification fails because token is used
    second_check = await token_manager.verify_token(token)
    assert second_check is None


@pytest.mark.asyncio
async def test_execute_actions_and_audit_logging(
    token_manager: ActionTokenManager,
    repos: RepositoryContainer,
    test_settings: Settings,
    setup_circle: tuple[CareCircle, Elder, Medication, Member],
):
    circle, _elder, med, caregiver = setup_circle
    audit = AuditService(repositories=repos)
    email_sender = FakeEmailSender()
    med_service = MedicationService(repositories=repos, audit_service=audit)

    # 1. Execute "took_it"
    token1 = token_manager.create_action_token(
        circle_id=circle.id,
        medication_id=med.id,
        scheduled_time="09:00",
        action="took_it",
    )
    payload1 = await token_manager.verify_token(token1)
    assert payload1 is not None

    await token_manager.execute_action(
        payload=payload1,
        medication_service=med_service,
        email_sender=email_sender,
        audit_service=audit,
    )

    # Verify dose was logged
    doses = await repos.dose_events.find(
        lambda d: d.circle_id == circle.id and d.medication_id == med.id
    )
    assert len(doses) == 1
    assert doses[0].status == "taken"

    # Verify audit log entry
    audit_entries = await repos.audit_log.find(lambda a: a.circle_id == circle.id)
    assert any(e.action == "action.took_it" for e in audit_entries)

    # Verify audit chain integrity
    is_valid, msg = await audit.verify_circle_chain(circle.id)
    assert is_valid is True, f"Audit chain verification failed: {msg}"

    # 2. Execute "call_me"
    token2 = token_manager.create_action_token(
        circle_id=circle.id,
        medication_id=med.id,
        scheduled_time="09:00",
        action="call_me",
    )
    payload2 = await token_manager.verify_token(token2)
    assert payload2 is not None

    await token_manager.execute_action(
        payload=payload2,
        medication_service=med_service,
        email_sender=email_sender,
        audit_service=audit,
    )

    # Check alert email dispatched to caregiver
    caregiver_emails = email_sender.get_emails_for(caregiver.email)
    assert len(caregiver_emails) == 1
    assert "call" in caregiver_emails[0]["subject"].lower()
