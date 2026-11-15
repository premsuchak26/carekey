"""Tests for Two-Key Rule approval, rejection, and emergency override workflows."""

import pytest

from app.models import ProposalStatus
from app.repositories import RepositoryContainer
from app.services.audit import AuditService
from app.services.proposals import ProposalService


@pytest.fixture
def proposal_service(test_repos: RepositoryContainer) -> ProposalService:
    audit_svc = AuditService(repositories=test_repos)
    return ProposalService(repositories=test_repos, audit_service=audit_svc)


@pytest.mark.asyncio
async def test_manager_proposal_creation_pending(
    proposal_service: ProposalService, test_repos: RepositoryContainer
) -> None:
    """Non-elder manager proposal remains PENDING without altering active medications."""
    proposal = await proposal_service.create_proposal(
        circle_id="circle-1",
        elder_id="elder-1",
        author_id="mgr-1",
        author_name="Nurse Bob",
        author_role="MANAGER",
        action="add",
        reason="Prescribed for blood pressure management",
        after={"name": "Lisinopril", "dosage": "10mg"},
    )

    assert proposal.status == ProposalStatus.PENDING
    assert proposal.is_emergency is False

    # Verify active medications repository has NOT been changed
    meds = await test_repos.medications.find(lambda m: m.circle_id == "circle-1")
    assert len(meds) == 0


@pytest.mark.asyncio
async def test_elder_approval_workflow_atomic(
    proposal_service: ProposalService, test_repos: RepositoryContainer
) -> None:
    """Elder approves pending proposal: change applies atomically and status updates to APPROVED."""
    proposal = await proposal_service.create_proposal(
        circle_id="circle-1",
        elder_id="elder-1",
        author_id="mgr-1",
        author_name="Nurse Bob",
        author_role="MANAGER",
        action="add",
        reason="Doctor recommended supplement",
        after={
            "name": "Vitamin D3",
            "dosage": "1000 IU",
            "schedule": {
                "times_of_day": ["09:00"],
                "dose_amount": "1 drop",
                "max_doses_per_day": 1,
            },
        },
    )

    updated_prop, applied_med = await proposal_service.approve_proposal(
        proposal_id=proposal.id,
        elder_id="elder-1",
        elder_name="Robert",
    )

    assert updated_prop.status == ProposalStatus.APPROVED
    assert updated_prop.resolved_by_name == "Robert"
    assert applied_med is not None
    assert applied_med.name == "Vitamin D3"

    # Verify medication now exists in circle repository
    circle_meds = await test_repos.medications.find(lambda m: m.circle_id == "circle-1")
    assert len(circle_meds) == 1
    assert circle_meds[0].name == "Vitamin D3"


@pytest.mark.asyncio
async def test_elder_rejection_workflow(
    proposal_service: ProposalService, test_repos: RepositoryContainer
) -> None:
    """Elder rejects pending proposal: stores rejection reason and does NOT apply change."""
    proposal = await proposal_service.create_proposal(
        circle_id="circle-1",
        elder_id="elder-1",
        author_id="mgr-1",
        author_name="Nurse Bob",
        author_role="MANAGER",
        action="add",
        reason="Alternative medication",
        after={"name": "Medication X", "dosage": "50mg"},
    )

    rejected_prop = await proposal_service.reject_proposal(
        proposal_id=proposal.id,
        elder_id="elder-1",
        elder_name="Robert",
        rejection_reason="I experience allergic reactions to this medication class.",
    )

    assert rejected_prop.status == ProposalStatus.REJECTED
    assert "allergic" in rejected_prop.rejection_reason.lower()

    # Verify no medication added
    circle_meds = await test_repos.medications.find(lambda m: m.circle_id == "circle-1")
    assert len(circle_meds) == 0


@pytest.mark.asyncio
async def test_emergency_override_success(
    proposal_service: ProposalService, test_repos: RepositoryContainer
) -> None:
    """Manager applies immediate change with written clinical reason under EMERGENCY_APPLIED."""
    prop, med = await proposal_service.emergency_override(
        circle_id="circle-1",
        elder_id="elder-1",
        author_id="mgr-1",
        author_name="Dr. Smith",
        author_role="MANAGER",
        action="add",
        emergency_reason="Acute hypertension crisis requiring immediate dosage initiation.",
        after={"name": "Clonidine", "dosage": "0.1mg"},
    )

    assert prop.status == ProposalStatus.EMERGENCY_APPLIED
    assert prop.is_emergency is True
    assert "hypertension" in prop.emergency_reason.lower()
    assert med is not None
    assert med.name == "Clonidine"

    # Verify applied directly
    circle_meds = await test_repos.medications.find(lambda m: m.circle_id == "circle-1")
    assert len(circle_meds) == 1
    assert circle_meds[0].name == "Clonidine"


@pytest.mark.asyncio
async def test_emergency_override_requires_reason(proposal_service: ProposalService) -> None:
    """Emergency override without a written reason raises ValueError."""
    with pytest.raises(ValueError, match="Emergency override requires a documented"):
        await proposal_service.emergency_override(
            circle_id="circle-1",
            elder_id="elder-1",
            author_id="mgr-1",
            author_name="Dr. Smith",
            author_role="MANAGER",
            action="add",
            emergency_reason="",  # Missing reason
            after={"name": "Clonidine", "dosage": "0.1mg"},
        )
