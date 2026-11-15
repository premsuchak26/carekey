"""Tests for healthcare appointments scheduling and management."""

from datetime import datetime, timedelta

import pytest

from app.config import Settings
from app.repositories import RepositoryContainer
from app.services.appointment import AppointmentService
from app.services.auth import AuthService


@pytest.mark.asyncio
async def test_appointment_lifecycle(
    test_repos: RepositoryContainer, test_settings: Settings
) -> None:
    """Verify adding, listing, updating, and deleting appointments."""
    auth = AuthService(repositories=test_repos, settings=test_settings)
    appt_service = AppointmentService(repositories=test_repos)

    circle, _, _ = await auth.create_circle(elder_name="Dorothy")
    now = datetime.now()

    # 1. Add upcoming appointment
    appt1 = await appt_service.add_appointment(
        circle_id=circle.id,
        doctor="Dr. Evans",
        place="City Medical Center",
        appointment_datetime=now + timedelta(days=2),
        notes="Blood pressure check",
    )
    assert appt1.doctor == "Dr. Evans"
    assert appt1.circle_id == circle.id

    # 2. Add past appointment
    _ = await appt_service.add_appointment(
        circle_id=circle.id,
        doctor="Dr. Wong",
        place="Dental Care",
        appointment_datetime=now - timedelta(days=5),
        notes="Routine cleaning",
    )

    # 3. List all vs upcoming only
    all_appts = await appt_service.list_appointments(circle.id, upcoming_only=False)
    assert len(all_appts) == 2

    upcoming = await appt_service.list_appointments(circle.id, upcoming_only=True)
    assert len(upcoming) == 1
    assert upcoming[0].id == appt1.id

    # 4. Update appointment
    updated = await appt_service.update_appointment(
        circle_id=circle.id,
        appointment_id=appt1.id,
        doctor="Dr. Evans (Cardiology)",
        place="Suite 404",
        appointment_datetime=now + timedelta(days=3),
        notes="Bring ECG records",
    )
    assert updated is not None
    assert updated.doctor == "Dr. Evans (Cardiology)"
    assert updated.place == "Suite 404"

    # 5. Delete appointment
    deleted = await appt_service.delete_appointment(circle.id, appt1.id)
    assert deleted is True

    remaining = await appt_service.list_appointments(circle.id, upcoming_only=True)
    assert len(remaining) == 0
