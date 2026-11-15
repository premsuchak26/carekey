"""End-to-end integration test of real application wiring across all features.

Flow:
1. Elder creates care circle with email and timezone.
2. Elder logs in with circle code and owner passcode.
3. Elder issues MANAGER key with validated email.
4. MANAGER logs in and proposes medication change.
5. Elder reviews and approves proposal (atomic application via Two-Key Rule).
6. Tick is executed via POST /internal/tick with secret header and fake email sender.
7. Elder receives reminder email with one-tap action link.
8. Elder confirms and executes one-tap action via POST /actions/execute with CSRF.
9. Dose is recorded as taken.
10. Tamper-evident audit chain verifies unbroken.
"""

import asyncio
import datetime as dt
import re
from zoneinfo import ZoneInfo

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.config import Settings
from app.repositories import RepositoryContainer
from app.routes.dependencies import get_email_sender
from app.services.audit import AuditService
from app.services.email import FakeEmailSender
from app.services.session import SessionManager


@pytest.fixture
def fake_email() -> FakeEmailSender:
    return FakeEmailSender()


def test_full_e2e_application_wiring(
    client: TestClient,
    test_repos: RepositoryContainer,
    test_settings: Settings,
    fake_email: FakeEmailSender,
) -> None:
    # Wire fake email sender into FastAPI dependency overrides
    client.app.dependency_overrides[get_email_sender] = lambda: fake_email
    session_mgr = SessionManager(settings=test_settings)
    audit = AuditService(repositories=test_repos)

    # 1. Elder creates Care Circle
    res_circle = client.post(
        "/circle/create",
        data={
            "elder_name": "Kavita Patel",
            "elder_email": "kavita.patel@example.com",
            "circle_name": "Patel Family Care",
            "timezone": "Asia/Kolkata",
        },
    )
    assert res_circle.status_code == status.HTTP_200_OK
    html = res_circle.text

    # Extract circle code and owner passcode
    code_match = re.search(r"CARE-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}", html)
    assert code_match, "Circle code not found in response HTML"
    circle_code = code_match.group(0)

    passcode_match = re.search(r'data-passcode="([23456789ABCDEFGHJKMNPQRSTUVWXYZ]{12})"', html)
    assert passcode_match, "Owner passcode not found in response HTML"
    elder_passcode = passcode_match.group(1)

    # 2. Elder logs in
    client.cookies.clear()
    res_login = client.post(
        "/login",
        data={"circle_code": circle_code, "passcode": elder_passcode},
        follow_redirects=False,
    )
    assert res_login.status_code == status.HTTP_303_SEE_OTHER
    assert res_login.headers["location"] == "/today"
    elder_cookie = res_login.cookies.get(session_mgr.COOKIE_NAME) or client.cookies.get(
        session_mgr.COOKIE_NAME
    )
    assert elder_cookie is not None, (
        f"Cookie not set: res={res_login.cookies}, client={client.cookies}"
    )
    elder_session = session_mgr.verify_session_token(elder_cookie)
    assert elder_session is not None
    elder_member_id = elder_session["member_id"]
    csrf_elder = session_mgr.generate_csrf_token(elder_member_id)

    res_issue = client.post(
        "/keys/issue",
        data={
            "csrf_token": csrf_elder,
            "name": "Priya (Daughter)",
            "email": "priya.patel@example.com",
            "role": "MANAGER",
            "validity_days": 30,
        },
    )
    assert res_issue.status_code == status.HTTP_200_OK
    priya_passcode_match = re.search(
        r'data-passcode="([23456789ABCDEFGHJKMNPQRSTUVWXYZ]{12})"', res_issue.text
    )
    assert priya_passcode_match, "Manager passcode not found in response HTML"
    priya_passcode = priya_passcode_match.group(1)

    # 4. Priya logs in as MANAGER
    client.cookies.clear()
    res_login_mgr = client.post(
        "/login",
        data={"circle_code": circle_code, "passcode": priya_passcode},
        follow_redirects=False,
    )
    assert res_login_mgr.status_code == status.HTTP_303_SEE_OTHER
    assert res_login_mgr.headers["location"] == "/dashboard"
    mgr_cookie = client.cookies.get(session_mgr.COOKIE_NAME)
    assert mgr_cookie is not None

    mgr_session = session_mgr.verify_session_token(mgr_cookie)
    assert mgr_session is not None
    csrf_mgr = session_mgr.generate_csrf_token(mgr_session["member_id"])

    # 5. Priya proposes adding Atorvastatin 20mg at 08:00
    res_prop = client.post(
        "/medications/add",
        data={
            "csrf_token": csrf_mgr,
            "name": "Atorvastatin",
            "dosage": "20mg",
            "instructions": "Take 1 tablet every morning with water",
            "prescribing_doctor": "Dr. Mehta",
            "times_of_day": "08:00",
            "days_of_week": "0,1,2,3,4,5,6",
            "proposal_reason": "Cardiologist prescribed for cholesterol management",
        },
        follow_redirects=False,
    )
    # Should redirect with message that proposal was submitted
    assert res_prop.status_code == status.HTTP_303_SEE_OTHER
    assert (
        "Proposal+submitted" in res_prop.headers["location"]
        or "proposals" in res_prop.headers["location"]
    )

    # Verify change proposal is pending in repo
    proposals = list(test_repos.proposals._storage.values())
    assert len(proposals) == 1
    assert proposals[0].status == "PENDING"
    assert proposals[0].after is not None
    assert proposals[0].after.get("name") == "Atorvastatin"
    proposal_id = proposals[0].id

    # 6. Elder logs back in and approves proposal
    client.cookies.clear()
    client.post(
        "/login",
        data={"circle_code": circle_code, "passcode": elder_passcode},
        follow_redirects=False,
    )
    res_approve = client.post(
        f"/proposals/{proposal_id}/approve",
        data={"csrf_token": csrf_elder},
        follow_redirects=False,
    )
    assert res_approve.status_code == status.HTTP_303_SEE_OTHER

    # Verify medication now exists in medications repository
    meds = list(test_repos.medications._storage.values())
    assert len(meds) == 1
    assert meds[0].name == "Atorvastatin"
    assert meds[0].schedule is not None
    assert "08:00" in meds[0].schedule.times_of_day

    # 7. Run POST /internal/tick at 07:55 AM Asia/Kolkata (5 min before 08:00 dose)
    # Without valid secret: 401 Unauthorized
    res_tick_bad = client.post(
        "/internal/tick",
        headers={"X-Internal-Secret": "wrong-secret"},
    )
    assert res_tick_bad.status_code == status.HTTP_401_UNAUTHORIZED

    # With valid secret header and simulated fake clock at 07:55 AM (5 min before 08:00 dose):
    tz = ZoneInfo("Asia/Kolkata")
    time_tick = dt.datetime(2026, 11, 15, 7, 55, tzinfo=tz)
    res_tick = client.post(
        "/internal/tick",
        params={"now": time_tick.isoformat()},
        headers={"X-Internal-Secret": test_settings.tick_secret},
    )
    assert res_tick.status_code == status.HTTP_200_OK
    tick_json = res_tick.json()
    assert tick_json["status"] == "ok"
    assert tick_json["sent_reminders"] >= 1

    # 8. Elder receives reminder email with one-tap action link
    kavita_emails = fake_email.get_emails_for("kavita.patel@example.com")
    assert len(kavita_emails) >= 1
    reminder_html = kavita_emails[0]["html_body"]
    assert "Atorvastatin" in reminder_html

    # Extract action token for "I Took It"
    token_match = re.search(r"/actions/confirm\?token=([^'\"\s>]+)", reminder_html)
    assert token_match, "Action token link not found in email HTML"
    action_token = token_match.group(1)

    # 9. Elder visits GET /actions/confirm?token=...
    res_confirm_page = client.get(f"/actions/confirm?token={action_token}")
    assert res_confirm_page.status_code == status.HTTP_200_OK
    assert "Atorvastatin" in res_confirm_page.text

    # Extract CSRF token from confirmation page
    action_csrf_match = re.search(r'name="csrf_token" value="([a-f0-9]+)"', res_confirm_page.text)
    assert action_csrf_match, "CSRF token not found on action confirmation page"
    action_csrf = action_csrf_match.group(1)

    # 10. Elder submits POST /actions/execute
    res_exec = client.post(
        "/actions/execute",
        data={"token": action_token, "csrf_token": action_csrf},
    )
    assert res_exec.status_code == status.HTTP_200_OK
    assert "Action Completed" in res_exec.text

    # 11. Verify dose event was logged in repository
    doses = list(test_repos.dose_events._storage.values())
    assert len(doses) == 1
    assert doses[0].status == "taken"
    assert doses[0].medication_id == meds[0].id

    # 12. Verify tamper-evident audit chain verifies unbroken
    circle = next(iter(test_repos.circles._storage.values()))
    is_valid, msg = asyncio.run(audit.verify_circle_chain(circle.id))
    assert is_valid is True, f"Audit chain verification failed: {msg}"
