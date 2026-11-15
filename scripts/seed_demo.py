"""Seed a demo CareCircle with an elder, caretakers, sample medications and appointments.

Outputs circle credentials and passcodes for immediate local testing or Cloud Run verification.

Usage:
    python -m scripts.seed_demo
    python scripts/seed_demo.py
"""

import asyncio
import datetime as dt
import sys
from pathlib import Path

# Ensure repository root is on sys.path for direct script execution
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import Settings, get_settings  # noqa: E402
from app.models import Appointment, MemberRole  # noqa: E402
from app.repositories import RepositoryContainer  # noqa: E402
from app.services.audit import AuditService  # noqa: E402
from app.services.auth import AuthService  # noqa: E402
from app.services.medication import MedicationService  # noqa: E402


async def seed_demo(settings: Settings | None = None) -> dict[str, str]:
    """Populate repository with demo elder, caretakers, and medications."""
    if settings is None:
        settings = get_settings()

    repos = RepositoryContainer(settings=settings)
    audit_service = AuditService(repositories=repos)
    auth_service = AuthService(repositories=repos, settings=settings, audit_service=audit_service)
    med_service = MedicationService(repositories=repos, audit_service=audit_service)

    # 1. Create Demo CareCircle for Elder
    elder_name = "Savitri Devi"
    elder_email = "savitri.devi@example.com"
    timezone = "Asia/Kolkata"

    circle, elder, elder_passcode = await auth_service.create_circle(
        elder_name=elder_name,
        elder_email=elder_email,
        timezone=timezone,
    )

    # 2. Issue Caretaker (Manager) Passcode
    manager_member, manager_passcode = await auth_service.issue_member_key(
        circle_id=circle.id,
        name="Rahul Sharma (Family Caregiver)",
        email="rahul.caretaker@example.com",
        role=MemberRole.MANAGER,
        actor_name=elder.name,
    )

    # 3. Issue Helper Passcode
    helper_member, helper_passcode = await auth_service.issue_member_key(
        circle_id=circle.id,
        name="Pooja Patel (Visiting Nurse)",
        email="pooja.nurse@example.com",
        role=MemberRole.HELPER,
        actor_name=elder.name,
    )

    # 4. Add Sample Medications
    # Medication 1: Amlodipine 5mg (Morning BP)
    med1 = await med_service.add_medication(
        circle_id=circle.id,
        name="Amlodipine",
        dosage="5mg",
        instructions="Take 1 tablet every morning with water.",
        prescribing_doctor="Dr. K. S. Sharma (Cardiology)",
        times_of_day=["08:00"],
        days_of_week=[0, 1, 2, 3, 4, 5, 6],
        dose_amount="1 tablet",
        actor_name=elder.name,
    )

    # Medication 2: Metformin 500mg (Morning & Evening Diabetes)
    await med_service.add_medication(
        circle_id=circle.id,
        name="Metformin",
        dosage="500mg",
        instructions="Take 1 tablet twice daily after meals.",
        prescribing_doctor="Dr. Ananya Ray (Endocrinology)",
        times_of_day=["09:00", "20:00"],
        days_of_week=[0, 1, 2, 3, 4, 5, 6],
        dose_amount="1 tablet",
        actor_name=elder.name,
    )

    # Medication 3: Atorvastatin 10mg (Bedtime Cholesterol)
    await med_service.add_medication(
        circle_id=circle.id,
        name="Atorvastatin",
        dosage="10mg",
        instructions="Take 1 tablet at night before sleep.",
        prescribing_doctor="Dr. K. S. Sharma (Cardiology)",
        times_of_day=["21:00"],
        days_of_week=[0, 1, 2, 3, 4, 5, 6],
        dose_amount="1 tablet",
        actor_name=elder.name,
    )

    # 5. Add Sample Healthcare Appointment
    appt_time = dt.datetime.now() + dt.timedelta(days=3, hours=4)
    appt = Appointment(
        circle_id=circle.id,
        doctor="Dr. K. S. Sharma (Cardiologist)",
        place="City Heart Care Clinic, Room 304",
        datetime=appt_time,
        notes="Routine 3-month blood pressure review and ECG checkup.",
    )
    await repos.appointments.save(appt.id, appt)

    # 6. Log Sample Dose Event (yesterday's taken dose)
    yesterday_morning = dt.datetime.now() - dt.timedelta(days=1)
    await med_service.log_dose(
        circle_id=circle.id,
        medication_id=med1.id,
        scheduled_time=yesterday_morning.replace(hour=8, minute=0, second=0, microsecond=0),
        status="taken",
        logged_by=elder.name,
        notes="Taken with breakfast",
        dose_status="on_time",
    )

    # Output formatted credentials
    base_url = settings.app_base_url.rstrip("/")
    login_url = f"{base_url}/login"

    border = "=" * 64
    print("\n" + border)
    print(" CareKey Demo Circle Created Successfully! ")
    print(border)
    print(f"Backend Storage:  {settings.repository_backend.upper()}")
    print(f"Circle Code:      {circle.circle_code}")
    print(f"Elder Name:       {elder.name} ({elder.email})")
    print(f"Elder Timezone:   {elder.timezone}")
    print("-" * 64)
    print("ELDER CREDENTIALS (Owner):")
    print(f"  Circle Code:    {circle.circle_code}")
    print(f"  Passcode:       {elder_passcode}")
    print(f"  Login URL:      {login_url}")
    print("-" * 64)
    print("CARETAKER CREDENTIALS (Manager - 2-Key & Proposals):")
    print(f"  Name:           {manager_member.name}")
    print(f"  Email:          {manager_member.email}")
    print(f"  Role:           {manager_member.role.value}")
    print(f"  Circle Code:    {circle.circle_code}")
    print(f"  Passcode:       {manager_passcode}")
    print("-" * 64)
    print("HELPER CREDENTIALS (Dose & Notes Logger):")
    print(f"  Name:           {helper_member.name}")
    print(f"  Email:          {helper_member.email}")
    print(f"  Role:           {helper_member.role.value}")
    print(f"  Circle Code:    {circle.circle_code}")
    print(f"  Passcode:       {helper_passcode}")
    print("-" * 64)
    print("SAMPLE MEDICATIONS ADDED:")
    print("  1. Amlodipine 5mg   - 08:00 (Daily)")
    print("  2. Metformin 500mg  - 09:00, 20:00 (Daily)")
    print("  3. Atorvastatin 10mg - 21:00 (Daily)")
    print("-" * 64)
    print(f"UPCOMING APPOINTMENT: {appt.doctor} on {appt_time.strftime('%Y-%m-%d %H:%M')}")
    print(border + "\n")

    return {
        "circle_code": circle.circle_code,
        "elder_passcode": elder_passcode,
        "manager_passcode": manager_passcode,
        "helper_passcode": helper_passcode,
    }


def main() -> None:
    """CLI entrypoint."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(seed_demo())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
