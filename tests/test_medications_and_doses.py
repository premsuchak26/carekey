"""Tests for medication scheduling, dose status computation, and adherence metrics."""

from datetime import datetime, timedelta

import pytest

from app.config import Settings
from app.repositories import RepositoryContainer
from app.services.auth import AuthService
from app.services.medication import MedicationService


def test_dose_status_calculation() -> None:
    """Verify punctual, late, missed, and skipped dose status transitions."""
    scheduled = datetime(2026, 11, 15, 8, 0, 0)

    # 1. Taken on time (exact)
    assert (
        MedicationService.calculate_dose_status(
            scheduled_time=scheduled,
            timestamp=scheduled,
            status="taken",
        )
        == "on_time"
    )

    # 2. Taken 25 minutes late (within 30 minute grace period)
    assert (
        MedicationService.calculate_dose_status(
            scheduled_time=scheduled,
            timestamp=scheduled + timedelta(minutes=25),
            status="taken",
        )
        == "on_time"
    )

    # 3. Taken 35 minutes late (over 30 minutes, but within 2 hours -> late)
    assert (
        MedicationService.calculate_dose_status(
            scheduled_time=scheduled,
            timestamp=scheduled + timedelta(minutes=35),
            status="taken",
        )
        == "late"
    )

    # 4. Taken 1 hour and 50 minutes late (under 2 hours -> late)
    assert (
        MedicationService.calculate_dose_status(
            scheduled_time=scheduled,
            timestamp=scheduled + timedelta(minutes=110),
            status="taken",
        )
        == "late"
    )

    # 5. Taken 2 hours and 15 minutes late (over 2 hours -> missed)
    assert (
        MedicationService.calculate_dose_status(
            scheduled_time=scheduled,
            timestamp=scheduled + timedelta(minutes=135),
            status="taken",
        )
        == "missed"
    )

    # 6. Explicitly skipped
    assert (
        MedicationService.calculate_dose_status(
            scheduled_time=scheduled,
            timestamp=scheduled + timedelta(minutes=5),
            status="skipped",
        )
        == "skipped"
    )


@pytest.mark.asyncio
async def test_adherence_summary_and_streak(
    test_repos: RepositoryContainer, test_settings: Settings
) -> None:
    """Verify medication adherence rate and streak tracking."""
    auth = AuthService(repositories=test_repos, settings=test_settings)
    med_service = MedicationService(repositories=test_repos)

    circle, _, _ = await auth.create_circle(elder_name="Harold")
    med = await med_service.add_medication(
        circle_id=circle.id,
        name="Metoprolol",
        dosage="50mg",
        times_of_day=["08:00"],
    )

    base_time = datetime(2026, 11, 10, 8, 0, 0)

    # Day 1: on time (taken)
    await med_service.log_dose(
        circle_id=circle.id,
        medication_id=med.id,
        scheduled_time=base_time,
        status="taken",
        timestamp=base_time + timedelta(minutes=5),
    )

    # Day 2: late (taken)
    await med_service.log_dose(
        circle_id=circle.id,
        medication_id=med.id,
        scheduled_time=base_time + timedelta(days=1),
        status="taken",
        timestamp=base_time + timedelta(days=1, minutes=45),
    )

    # Day 3: on time (taken)
    await med_service.log_dose(
        circle_id=circle.id,
        medication_id=med.id,
        scheduled_time=base_time + timedelta(days=2),
        status="taken",
        timestamp=base_time + timedelta(days=2, minutes=10),
    )

    # 3 doses taken in a row -> streak should be 3
    summaries = await med_service.get_adherence_summary(circle.id)
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.total_doses == 3
    assert summary.taken_doses == 3
    assert summary.on_time_doses == 2
    assert summary.late_doses == 1
    assert summary.missed_doses == 0
    assert summary.adherence_percentage == 100.0
    assert summary.streak_days == 3

    overall_streak = await med_service.get_overall_streak(circle.id)
    assert overall_streak == 3

    # Day 4: skipped (breaks the streak)
    await med_service.log_dose(
        circle_id=circle.id,
        medication_id=med.id,
        scheduled_time=base_time + timedelta(days=3),
        status="skipped",
        timestamp=base_time + timedelta(days=3, minutes=10),
    )

    # After skipped dose, streak should be 0
    summaries_after = await med_service.get_adherence_summary(circle.id)
    assert summaries_after[0].streak_days == 0
    assert summaries_after[0].total_doses == 4
    assert summaries_after[0].taken_doses == 3
    assert summaries_after[0].skipped_doses == 1
    assert summaries_after[0].adherence_percentage == 75.0
