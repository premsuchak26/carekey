"""Integration tests verifying full HTTP user journeys and UI flows."""

from fastapi import status
from fastapi.testclient import TestClient

from app.config import Settings
from app.repositories import RepositoryContainer
from app.services.session import SessionManager


def test_full_elder_and_caretaker_flow(
    client: TestClient, test_repos: RepositoryContainer, test_settings: Settings
) -> None:
    """Test full workflow: create circle -> login -> view today -> take dose -> check dashboard."""
    session_mgr = SessionManager(settings=test_settings)

    # 1. Elder creates circle
    res_create = client.post(
        "/circle/create",
        data={"elder_name": "Rose Dawson", "circle_name": "Rose Care Circle"},
    )
    assert res_create.status_code == status.HTTP_200_OK
    assert "Your Care Circle is Ready" in res_create.text
    assert "CARE-" in res_create.text

    # Extract circle code
    import asyncio

    circles = asyncio.run(test_repos.circles.find(lambda c: c.name == "Rose Care Circle"))
    assert len(circles) == 1
    circle = circles[0]

    # Find owner member
    members = asyncio.run(test_repos.members.find(lambda m: m.circle_id == circle.id))
    assert len(members) == 1
    owner = members[0]

    # Log in as Elder
    token = session_mgr.create_session_token(
        circle_id=circle.id,
        member_id=owner.id,
        role=owner.role.value,
        member_name=owner.name,
    )
    client.cookies.set(session_mgr.COOKIE_NAME, token)
    csrf = session_mgr.generate_csrf_token(owner.id)

    # 2. Add Medication as Elder
    res_add_med = client.post(
        "/medications/add",
        data={
            "name": "Levothyroxine",
            "dosage": "50mcg",
            "times_of_day": "08:00",
            "dose_amount": "1 tablet",
            "instructions": "Take before breakfast",
            "csrf_token": csrf,
        },
        follow_redirects=True,
    )
    assert res_add_med.status_code == status.HTTP_200_OK
    assert "Levothyroxine" in res_add_med.text

    # 3. View Today Screen
    res_today = client.get("/today")
    assert res_today.status_code == status.HTTP_200_OK
    assert "Today's Schedule" in res_today.text
    assert "Levothyroxine" in res_today.text
    assert "TAKE NOW" in res_today.text

    # Extract medication
    meds = asyncio.run(test_repos.medications.find(lambda m: m.circle_id == circle.id))
    assert len(meds) == 1
    med = meds[0]

    # 4. Take Dose via Big Button
    res_take = client.post(
        "/today/dose/take",
        data={
            "medication_id": med.id,
            "time_str": "08:00",
            "csrf_token": csrf,
        },
        follow_redirects=True,
    )
    assert res_take.status_code == status.HTTP_200_OK
    assert "Taken" in res_take.text

    # 5. View Caretaker Dashboard
    res_dash = client.get("/dashboard")
    assert res_dash.status_code == status.HTTP_200_OK
    assert "Care Circle Dashboard" in res_dash.text
    assert "1 / 1 Doses Taken" in res_dash.text
    assert "1 Dose Streak" in res_dash.text

    # 6. Issue a new Member Key for a Caretaker
    res_issue = client.post(
        "/keys/issue",
        data={
            "name": "Nurse Kelly",
            "role": "HELPER",
            "validity_days": 30,
            "csrf_token": csrf,
        },
    )
    assert res_issue.status_code == status.HTTP_200_OK
    assert "Newly Issued Access Key for Nurse Kelly" in res_issue.text
    assert "Nurse Kelly" in res_issue.text

    # 7. Add Appointment
    res_appt = client.post(
        "/appointments/add",
        data={
            "doctor": "Dr. Smith",
            "place": "Central Clinic",
            "datetime": "2026-11-20T10:30",
            "notes": "General checkup",
            "csrf_token": csrf,
        },
        follow_redirects=True,
    )
    assert res_appt.status_code == status.HTTP_200_OK
    assert "Dr. Smith" in res_appt.text
    assert "Central Clinic" in res_appt.text

    # 8. Test Manager Two-Key Proposal submission via HTTP
    from app.models import MemberRole

    kelly_members = asyncio.run(test_repos.members.find(lambda m: m.name == "Nurse Kelly"))
    assert len(kelly_members) == 1
    kelly = kelly_members[0]
    kelly.role = MemberRole.MANAGER
    asyncio.run(test_repos.members.save(kelly.id, kelly))

    # Create Manager session with real database member ID
    mgr_token = session_mgr.create_session_token(
        circle_id=circle.id,
        member_id=kelly.id,
        role=kelly.role.value,
        member_name=kelly.name,
    )
    client.cookies.set(session_mgr.COOKIE_NAME, mgr_token)
    mgr_csrf = session_mgr.generate_csrf_token(kelly.id)

    res_prop = client.post(
        "/medications/add",
        data={
            "name": "Aspirin",
            "dosage": "81mg",
            "reason": "Cardioprotection recommended",
            "csrf_token": mgr_csrf,
        },
        follow_redirects=True,
    )
    assert res_prop.status_code == status.HTTP_200_OK
    assert "Proposal submitted for Elder approval" in res_prop.text

    # Switch back to Elder session
    client.cookies.set(session_mgr.COOKIE_NAME, token)

    # 9. Elder views Today screen and sees pending proposal
    res_today_prop = client.get("/today")
    assert res_today_prop.status_code == status.HTTP_200_OK
    assert "Aspirin" in res_today_prop.text
    assert "Approve Change" in res_today_prop.text

    # 10. Check Audit Log History Page ("Who touched my health data")
    res_history = client.get("/history")
    assert res_history.status_code == status.HTTP_200_OK
    assert "Who Touched My Health Data" in res_history.text
    assert "Verify History" in res_history.text

    # 11. Verify History Cryptographic Chain
    res_verify = client.post(
        "/history/verify",
        data={"csrf_token": csrf},
    )
    assert res_verify.status_code == status.HTTP_200_OK
    assert "Audit Log Verified Intact" in res_verify.text
