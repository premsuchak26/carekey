"""Tests for append-only tamper-evident audit log and cryptographic chain verification."""

import datetime as dt

import pytest

from app.repositories import RepositoryContainer
from app.services.audit import GENESIS_HASH, AuditService, verify_chain


@pytest.fixture
def audit_service(test_repos: RepositoryContainer) -> AuditService:
    return AuditService(repositories=test_repos)


@pytest.mark.asyncio
async def test_audit_logs_all_required_events_and_no_passcodes(
    audit_service: AuditService, test_repos: RepositoryContainer
) -> None:
    """Verify logging of logins, keys, proposals, approvals, doses, and emergency overrides.

    Ensure passcodes and raw keys are strictly redacted/never recorded in plain text.
    """
    circle_id = "circle-audit-test"
    elder_id = "elder-audit-test"

    # 1. Login
    e1 = await audit_service.log_event(
        elder_id=elder_id,
        circle_id=circle_id,
        actor="Alice Elder",
        action="auth.login",
        target="CARE-TEST",
        details={"role": "ELDER", "passcode": "SECRET_PASSCODE_123"},
    )
    # Confirm passcode is redacted
    assert e1.details.get("passcode") == "[REDACTED]"
    assert "SECRET_PASSCODE" not in str(e1.details)

    # 2. Failed login
    e2 = await audit_service.log_event(
        elder_id=elder_id,
        circle_id=circle_id,
        actor="Unrecognized (192.168.1.10)",
        action="auth.login_failed",
        target="CARE-TEST",
        details={"client_ip": "192.168.1.10", "key": "ATTEMPTED_KEY_XYZ"},
    )
    assert e2.details.get("key") == "[REDACTED]"

    # 3. Key issue
    e3 = await audit_service.log_event(
        elder_id=elder_id,
        circle_id=circle_id,
        actor="Alice Elder",
        action="key.issue",
        target="Bob Caretaker",
        details={"member_name": "Bob Caretaker", "role": "MANAGER", "token": "KEY_SECRET"},
    )
    assert e3.details.get("token") == "[REDACTED]"

    # 4. Key revoke
    await audit_service.log_event(
        elder_id=elder_id,
        circle_id=circle_id,
        actor="Alice Elder",
        action="key.revoke",
        target="Bob Caretaker",
        details={"member_name": "Bob Caretaker"},
    )

    # 5. Proposal create
    await audit_service.log_event(
        elder_id=elder_id,
        circle_id=circle_id,
        actor="Bob Caretaker",
        action="proposal.create",
        target="Aspirin",
        details={"medication_name": "Aspirin", "action": "add", "risk_level": "LOW"},
    )

    # 6. Proposal approve
    await audit_service.log_event(
        elder_id=elder_id,
        circle_id=circle_id,
        actor="Alice Elder",
        action="proposal.approve",
        target="Aspirin",
        details={"medication_name": "Aspirin"},
    )

    # 7. Proposal reject
    await audit_service.log_event(
        elder_id=elder_id,
        circle_id=circle_id,
        actor="Alice Elder",
        action="proposal.reject",
        target="Lipitor",
        details={"medication_name": "Lipitor", "rejection_reason": "Not needed"},
    )

    # 8. Dose log
    await audit_service.log_event(
        elder_id=elder_id,
        circle_id=circle_id,
        actor="Bob Caretaker",
        action="dose.log",
        target="Aspirin",
        details={"status": "taken", "dose_status": "on_time"},
    )

    # 9. Emergency override
    await audit_service.log_event(
        elder_id=elder_id,
        circle_id=circle_id,
        actor="Bob Caretaker",
        action="emergency_override.medication",
        target="Aspirin",
        details={"action": "add", "reason": "Immediate allergic antidote"},
    )

    entries = await audit_service.get_entries(circle_id=circle_id)
    assert len(entries) == 9

    # Verify cryptographic integrity of the entire chain
    is_valid, message = await audit_service.verify_circle_chain(circle_id=circle_id)
    assert is_valid is True
    assert "intact" in message.lower()


@pytest.mark.asyncio
async def test_chain_verification_genesis_link(audit_service: AuditService) -> None:
    """The first entry in a chain must reference the genesis hash."""
    entry = await audit_service.log_event(
        elder_id="elder-1",
        circle_id="circle-genesis",
        actor="Elder",
        action="auth.login",
        target="CARE-0001",
    )
    assert entry.prev_hash == GENESIS_HASH


@pytest.mark.asyncio
async def test_tampered_entry_fails_verification(audit_service: AuditService) -> None:
    """Modifying an entry's contents or metadata after creation is detected as tampering."""
    circle_id = "circle-tamper-test"
    elder_id = "elder-tamper-test"

    t0 = dt.datetime.now()
    e1 = await audit_service.log_event(
        elder_id=elder_id,
        circle_id=circle_id,
        actor="Dr. Evans",
        action="dose.log",
        target="Insulin",
        details={"status": "taken", "units": 10},
        timestamp=t0,
    )
    e2 = await audit_service.log_event(
        elder_id=elder_id,
        circle_id=circle_id,
        actor="Dr. Evans",
        action="dose.log",
        target="Insulin",
        details={"status": "taken", "units": 10},
        timestamp=t0 + dt.timedelta(minutes=5),
    )

    entries = [e1, e2]
    # Initially valid
    valid, _ = verify_chain(entries)
    assert valid is True

    # Tamper with the details of e1 (e.g. adversary changing dosage)
    tampered_e1 = e1.model_copy(deep=True)
    tampered_e1.details["units"] = 50  # Changed 10 to 50 without updating hash

    tampered_entries = [tampered_e1, e2]
    is_valid, msg = verify_chain(tampered_entries)

    assert is_valid is False
    assert "tamper" in msg.lower() or "mismatch" in msg.lower()
    assert tampered_e1.id in msg


@pytest.mark.asyncio
async def test_tampered_prev_hash_link_fails_verification(audit_service: AuditService) -> None:
    """Modifying a prev_hash pointer is immediately caught as a broken chain link."""
    circle_id = "circle-link-test"
    elder_id = "elder-link-test"

    t0 = dt.datetime.now()
    e1 = await audit_service.log_event(
        elder_id=elder_id,
        circle_id=circle_id,
        actor="Alice",
        action="auth.login",
        target="CARE-1234",
        timestamp=t0,
    )
    e2 = await audit_service.log_event(
        elder_id=elder_id,
        circle_id=circle_id,
        actor="Alice",
        action="dose.log",
        target="Aspirin",
        timestamp=t0 + dt.timedelta(minutes=10),
    )

    # Break chain link
    tampered_e2 = e2.model_copy(deep=True)
    tampered_e2.prev_hash = "f" * 64

    is_valid, msg = verify_chain([e1, tampered_e2])
    assert is_valid is False
    assert "broken chain link" in msg.lower()
    assert tampered_e2.id in msg
