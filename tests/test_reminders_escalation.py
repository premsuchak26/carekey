"""Tests for reminder service, POST /internal/tick escalation ladder,
and appointment reminders.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from app.config import Settings
from app.models import Appointment, CareCircle, DoseSchedule, Elder, Medication, Member, MemberRole
from app.repositories import RepositoryContainer
from app.services.action_tokens import ActionTokenManager
from app.services.audit import AuditService
from app.services.email import FakeEmailSender
from app.services.medication import MedicationService
from app.services.reminders import ReminderService


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        app_name="CareKey-Test",
        environment="test",
        debug=True,
        repository_backend="memory",
        secret_key="secret-for-tokens",
        tick_secret="super-secret-tick-key",
        app_base_url="http://localhost:8000",
    )


@pytest.fixture
def repos(test_settings: Settings) -> RepositoryContainer:
    c = RepositoryContainer(test_settings)
    c.clear()
    return c


@pytest.fixture
def email_sender() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture
def reminder_service(
    repos: RepositoryContainer,
    test_settings: Settings,
    email_sender: FakeEmailSender,
) -> ReminderService:
    token_mgr = ActionTokenManager(settings=test_settings, repos=repos)
    audit = AuditService(repositories=repos)
    med_service = MedicationService(repositories=repos, audit_service=audit)
    return ReminderService(
        repos=repos,
        settings=test_settings,
        email_sender=email_sender,
        token_manager=token_mgr,
        medication_service=med_service,
        audit_service=audit,
    )


@pytest.mark.asyncio
async def test_escalation_ladder_10m_before_15m_late_60m_late(
    reminder_service: ReminderService,
    repos: RepositoryContainer,
    email_sender: FakeEmailSender,
):
    # Setup elder in Asia/Kolkata timezone
    tz = ZoneInfo("Asia/Kolkata")
    elder = Elder(name="Dadi", email="dadi@example.com", timezone="Asia/Kolkata")
    await repos.elders.save(elder.id, elder)

    circle = CareCircle(circle_code="CARE-DADI", elder_id=elder.id, name="Dadi Circle")
    await repos.circles.save(circle.id, circle)

    from uuid import uuid4

    med_id = str(uuid4())
    med = Medication(
        id=med_id,
        circle_id=circle.id,
        name="Metformin",
        dosage="500mg",
        schedule=DoseSchedule(
            medication_id=med_id, times_of_day=["09:00"], days_of_week=[0, 1, 2, 3, 4, 5, 6]
        ),
    )
    await repos.medications.save(med.id, med)

    caregiver = Member(
        circle_id=circle.id,
        name="Son Rahul",
        email="rahul@example.com",
        role=MemberRole.MANAGER,
        key_hash="hash",
        salt="salt",
    )
    await repos.members.save(caregiver.id, caregiver)

    # 1. Clock at 08:52 (8 minutes before 09:00 dose): should trigger elder_10m_before
    time_before = dt.datetime(2026, 11, 15, 8, 52, tzinfo=tz)
    res1 = await reminder_service.process_tick(now=time_before)
    assert res1["sent_reminders"] == 1

    dadi_emails = email_sender.get_emails_for("dadi@example.com")
    assert len(dadi_emails) == 1
    assert "Metformin" in dadi_emails[0]["subject"]
    # Check one-tap action links present in email
    assert "/actions/confirm?token=" in dadi_emails[0]["html_body"]

    # 2. Clock at 08:55 (still within 10m window, should be idempotent and NOT send another)
    time_before2 = dt.datetime(2026, 11, 15, 8, 55, tzinfo=tz)
    res2 = await reminder_service.process_tick(now=time_before2)
    assert res2["sent_reminders"] == 0
    assert len(email_sender.get_emails_for("dadi@example.com")) == 1

    # 3. Clock at 09:20 (20 minutes late): should trigger elder_15m_late nudge
    time_late = dt.datetime(2026, 11, 15, 9, 20, tzinfo=tz)
    res3 = await reminder_service.process_tick(now=time_late)
    assert res3["sent_reminders"] == 1
    assert len(email_sender.get_emails_for("dadi@example.com")) == 2

    # 4. Clock at 10:05 (65 minutes late): should trigger caretaker_60m_missed alert
    time_missed = dt.datetime(2026, 11, 15, 10, 5, tzinfo=tz)
    res4 = await reminder_service.process_tick(now=time_missed)
    assert res4["sent_reminders"] == 1

    # Caretaker should have received missed alert
    rahul_emails = email_sender.get_emails_for("rahul@example.com")
    assert len(rahul_emails) == 1
    assert "missed" in rahul_emails[0]["subject"].lower()

    # Dose should be marked missed in dose_events
    events = await repos.dose_events.find(
        lambda e: e.circle_id == circle.id and e.medication_id == med.id
    )
    assert len(events) == 1
    assert events[0].dose_status == "missed"


@pytest.mark.asyncio
async def test_appointment_reminders_24h_and_2h(
    reminder_service: ReminderService,
    repos: RepositoryContainer,
    email_sender: FakeEmailSender,
):
    tz = ZoneInfo("Asia/Kolkata")
    elder = Elder(name="Bapuji", email="bapuji@example.com", timezone="Asia/Kolkata")
    await repos.elders.save(elder.id, elder)

    circle = CareCircle(circle_code="CARE-BAPU", elder_id=elder.id, name="Bapu Circle")
    await repos.circles.save(circle.id, circle)

    app_time = dt.datetime(2026, 11, 16, 14, 0, tzinfo=tz)
    appt = Appointment(
        circle_id=circle.id,
        doctor="Dr. Sharma (Cardiology)",
        place="City Clinic Room 4",
        datetime=app_time,
        notes="Fast 4 hours before blood test",
    )
    await repos.appointments.save(appt.id, appt)

    # 1. 23 hours before appointment (Nov 15, 15:00): 24h reminder
    clock_23h = dt.datetime(2026, 11, 15, 15, 0, tzinfo=tz)
    res1 = await reminder_service.process_tick(now=clock_23h)
    assert res1["sent_reminders"] == 1
    bapu_emails = email_sender.get_emails_for("bapuji@example.com")
    assert len(bapu_emails) == 1
    assert "Dr. Sharma" in bapu_emails[0]["subject"]

    # 2. 1.5 hours before appointment (Nov 16, 12:30): 2h reminder
    clock_90m = dt.datetime(2026, 11, 16, 12, 30, tzinfo=tz)
    res2 = await reminder_service.process_tick(now=clock_90m)
    assert res2["sent_reminders"] == 1
    assert len(email_sender.get_emails_for("bapuji@example.com")) == 2
