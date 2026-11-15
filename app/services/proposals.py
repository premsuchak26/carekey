"""Two-key rule proposal service and pure risk scoring function."""

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models import (
    ChangeProposal,
    DoseSchedule,
    Medication,
    ProposalStatus,
    RiskLevel,
)
from app.repositories import RepositoryContainer
from app.services.audit import AuditService

_INGREDIENTS_FILE = Path(__file__).resolve().parent.parent / "data" / "ingredients.json"


def load_ingredients_table() -> dict[str, dict[str, Any]]:
    """Load the local JSON table of common active ingredients and daily maximums."""
    if not _INGREDIENTS_FILE.exists():
        return {}
    with open(_INGREDIENTS_FILE, encoding="utf-8") as f:
        data: dict[str, dict[str, Any]] = json.load(f)
        return data


def parse_dose_number(dosage_str: Any) -> float | None:
    """Extract numeric value from dosage string (e.g. '100mg', '2.5 mg', '2 tablets')."""
    if not dosage_str:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", str(dosage_str))
    if match:
        return float(match.group(1))
    return None


def match_ingredient(med_name: str, table: dict[str, dict[str, Any]]) -> tuple[str, float] | None:
    """Find active ingredient and daily maximum (mg) from medication name.

    Returns:
        tuple[str, float] | None: (active_ingredient_name, daily_max_mg) if recognized.
    """
    clean_name = med_name.lower().strip()
    for key, info in table.items():
        ingredient = info["ingredient"]
        daily_max = float(info.get("daily_max_mg", 0))
        # Direct key match or word boundary search
        if key in clean_name or ingredient in clean_name:
            return ingredient, daily_max
        # Check brand name aliases
        for brand in info.get("brand_names", []):
            if brand in clean_name:
                return ingredient, daily_max
    return None


def _check_removal(
    before: dict[str, Any] | None, after: dict[str, Any] | None
) -> tuple[bool, list[str]]:
    """Check if change represents medication removal (MEDIUM risk)."""
    if after is None or after.get("deleted") is True or after.get("action") == "delete":
        med_name = before.get("name", "medication") if before else "medication"
        return True, [
            f"Medication removal: '{med_name}' is proposed to be removed from the care regimen."
        ]
    return False, []


def _check_dosage_increase(
    before: dict[str, Any] | None, after: dict[str, Any] | None
) -> tuple[bool, list[str]]:
    """Check if single dose increases by more than 1.5x (HIGH risk)."""
    if before is not None and after is not None:
        before_dose = parse_dose_number(before.get("dosage") or before.get("dose_amount"))
        after_dose = parse_dose_number(after.get("dosage") or after.get("dose_amount"))
        if before_dose and after_dose and before_dose > 0:
            ratio = round(after_dose / before_dose, 2)
            if ratio > 1.5:
                return True, [
                    f"Dose increase of {ratio}x exceeds safety threshold of 1.5x "
                    f"(increased from {before_dose} to {after_dose})."
                ]
    return False, []


def _extract_daily_frequency(after: dict[str, Any]) -> tuple[int, int]:
    """Extract daily dose frequency and maximum allowed daily doses."""
    after_sched = after.get("schedule")
    if isinstance(after_sched, dict):
        times = after_sched.get("times_of_day", ["08:00"])
        max_allowed = int(after_sched.get("max_doses_per_day", 1))
    else:
        times = after.get("times_of_day", ["08:00"])
        max_allowed = int(after.get("max_doses_per_day", 1))
    daily_freq = len(times) if isinstance(times, list) else 1
    return daily_freq, max_allowed


def _check_active_ingredients(
    after: dict[str, Any],
    daily_frequency: int,
    existing_medications: list[dict[str, Any]] | list[Medication] | None,
    current_med_id: str | None,
    table: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Check for duplicate active ingredients or daily maximum exceedances."""
    reasons: list[str] = []
    is_high = False
    after_name = after.get("name", "")
    after_dose_val = parse_dose_number(after.get("dosage") or after.get("dose_amount"))
    after_ingredient_info = match_ingredient(after_name, table)

    if not after_ingredient_info:
        return False, []

    active_ing, max_daily_mg = after_ingredient_info

    # Rule 4: Exceeds daily maximum
    if after_dose_val and max_daily_mg > 0:
        total_daily_mg = after_dose_val * daily_frequency
        if total_daily_mg > max_daily_mg:
            reasons.append(
                f"Proposed daily intake of {total_daily_mg}mg exceeds recommended daily "
                f"maximum ({max_daily_mg}mg) for active ingredient '{active_ing}'."
            )
            is_high = True

    # Rule 3: Same active ingredient as an existing one (duplicate therapy)
    if existing_medications:
        for item in existing_medications:
            item_dict = item.model_dump() if isinstance(item, Medication) else item
            if current_med_id and item_dict.get("id") == current_med_id:
                continue
            other_name = item_dict.get("name", "")
            other_match = match_ingredient(other_name, table)
            if other_match and other_match[0] == active_ing:
                reasons.append(
                    f"Duplicate active ingredient: '{active_ing}' is already prescribed in "
                    f"active medication '{other_name}'."
                )
                is_high = True
                break

    return is_high, reasons


def risk_score(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    existing_medications: list[dict[str, Any]] | list[Medication] | None = None,
) -> tuple[RiskLevel, list[str]]:
    """Calculate proposal risk level (LOW, MEDIUM, HIGH) with plain-language reasons."""
    reasons: list[str] = []
    is_high = False
    is_medium = False

    table = load_ingredients_table()

    # Rule 6: Medication removal
    is_del, del_reasons = _check_removal(before, after)
    if is_del:
        return RiskLevel.MEDIUM, del_reasons

    # Rule 2: New medication
    if before is None and after is not None:
        med_name = after.get("name", "New medication")
        reasons.append(f"New medication: '{med_name}' is being added to the elder's regimen.")
        is_medium = True

    # Rule 1: Dose increase over 1.5x
    dose_high, dose_reasons = _check_dosage_increase(before, after)
    if dose_high:
        is_high = True
        reasons.extend(dose_reasons)

    if after is not None:
        daily_freq, max_allowed = _extract_daily_frequency(after)
        # Rule 5: More doses per day than allowed
        if daily_freq > max_allowed:
            reasons.append(
                f"More doses per day ({daily_freq}) scheduled than max allowed ({max_allowed})."
            )
            is_high = True

        current_med_id = (before or {}).get("id") or after.get("id")
        ing_high, ing_reasons = _check_active_ingredients(
            after, daily_freq, existing_medications, current_med_id, table
        )
        if ing_high:
            is_high = True
        reasons.extend(ing_reasons)

    if is_high:
        return RiskLevel.HIGH, reasons
    if is_medium:
        return RiskLevel.MEDIUM, reasons

    if not reasons:
        reasons.append("Routine medication or schedule adjustment with no high-risk flags.")
    return RiskLevel.LOW, reasons


class ProposalService:
    """Service handling two-key change proposals, risk assessment, and approvals."""

    def __init__(self, repositories: RepositoryContainer, audit_service: AuditService) -> None:
        self.repos = repositories
        self.audit = audit_service

    async def create_proposal(
        self,
        circle_id: str,
        elder_id: str,
        author_id: str,
        author_name: str,
        author_role: str,
        action: str,
        reason: str,
        target_type: str = "medication",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> ChangeProposal:
        """Create a pending two-key change proposal with risk scoring and audit logging."""
        existing_meds = await self.repos.medications.find(lambda m: m.circle_id == circle_id)
        risk, reasons = risk_score(before=before, after=after, existing_medications=existing_meds)

        proposal = ChangeProposal(
            circle_id=circle_id,
            elder_id=elder_id,
            author_id=author_id,
            author_name=author_name,
            author_role=author_role,
            target_type="schedule" if target_type == "schedule" else "medication",
            action="delete" if action == "delete" else ("edit" if action == "edit" else "add"),
            before=before,
            after=after,
            reason=reason,
            status=ProposalStatus.PENDING,
            risk_level=risk,
            risk_reasons=reasons,
            is_emergency=False,
        )
        await self.repos.proposals.save(proposal.id, proposal)
        saved = proposal

        # Audit proposal creation (passwords/keys never logged)
        med_name = (after or before or {}).get("name", "medication")
        await self.audit.log_event(
            elder_id=elder_id,
            circle_id=circle_id,
            actor=author_name,
            action="proposal.create",
            target=saved.id,
            details={
                "proposal_id": saved.id,
                "medication_name": med_name,
                "action": action,
                "risk_level": risk.value,
                "reason": reason,
                "risk_reasons": reasons,
            },
        )
        return saved

    async def emergency_override(
        self,
        circle_id: str,
        elder_id: str,
        author_id: str,
        author_name: str,
        author_role: str,
        action: str,
        emergency_reason: str,
        target_type: str = "medication",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> tuple[ChangeProposal, Medication | None]:
        """Apply a change immediately under emergency override with written justification."""
        if not emergency_reason or not emergency_reason.strip():
            raise ValueError(
                "Emergency override requires a documented clinical/care justification."
            )

        existing_meds = await self.repos.medications.find(lambda m: m.circle_id == circle_id)
        risk, reasons = risk_score(before=before, after=after, existing_medications=existing_meds)

        proposal = ChangeProposal(
            circle_id=circle_id,
            elder_id=elder_id,
            author_id=author_id,
            author_name=author_name,
            author_role=author_role,
            target_type="schedule" if target_type == "schedule" else "medication",
            action="delete" if action == "delete" else ("edit" if action == "edit" else "add"),
            before=before,
            after=after,
            reason=emergency_reason,
            status=ProposalStatus.EMERGENCY_APPLIED,
            risk_level=risk,
            risk_reasons=reasons,
            is_emergency=True,
            emergency_reason=emergency_reason.strip(),
            resolved_at=dt.datetime.now(),
            resolved_by_id=author_id,
            resolved_by_name=author_name,
        )
        await self.repos.proposals.save(proposal.id, proposal)
        saved_proposal = proposal

        # Apply change directly to repository
        applied_med = await self._apply_change(
            circle_id=circle_id, action=action, before=before, after=after
        )

        med_name = (after or before or {}).get("name", "medication")
        await self.audit.log_event(
            elder_id=elder_id,
            circle_id=circle_id,
            actor=author_name,
            action="emergency_override.medication",
            target=med_name,
            details={
                "proposal_id": saved_proposal.id,
                "medication_name": med_name,
                "action": action,
                "reason": emergency_reason.strip(),
                "risk_level": risk.value,
            },
        )
        return saved_proposal, applied_med

    async def approve_proposal(
        self, proposal_id: str, elder_id: str, elder_name: str
    ) -> tuple[ChangeProposal, Medication | None]:
        """Elder approves a pending change proposal; applies changes atomically."""
        proposal = await self.repos.proposals.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal '{proposal_id}' not found.")
        if proposal.status != ProposalStatus.PENDING:
            raise ValueError(f"Proposal is already resolved with status '{proposal.status}'.")

        applied_med = await self._apply_change(
            circle_id=proposal.circle_id,
            action=proposal.action,
            before=proposal.before,
            after=proposal.after,
        )

        proposal.status = ProposalStatus.APPROVED
        proposal.resolved_at = dt.datetime.now()
        proposal.resolved_by_id = elder_id
        proposal.resolved_by_name = elder_name
        await self.repos.proposals.save(proposal.id, proposal)
        updated = proposal

        med_name = (proposal.after or proposal.before or {}).get("name", "medication")
        await self.audit.log_event(
            elder_id=proposal.elder_id,
            circle_id=proposal.circle_id,
            actor=elder_name,
            action="proposal.approve",
            target=med_name,
            details={
                "proposal_id": proposal.id,
                "medication_name": med_name,
                "action": proposal.action,
            },
        )
        return updated, applied_med

    async def reject_proposal(
        self, proposal_id: str, elder_id: str, elder_name: str, rejection_reason: str
    ) -> ChangeProposal:
        """Elder rejects a pending change proposal with reason."""
        proposal = await self.repos.proposals.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal '{proposal_id}' not found.")
        if proposal.status != ProposalStatus.PENDING:
            raise ValueError(f"Proposal is already resolved with status '{proposal.status}'.")

        proposal.status = ProposalStatus.REJECTED
        proposal.rejection_reason = rejection_reason.strip() or "Rejected by elder."
        proposal.resolved_at = dt.datetime.now()
        proposal.resolved_by_id = elder_id
        proposal.resolved_by_name = elder_name
        await self.repos.proposals.save(proposal.id, proposal)
        updated = proposal

        med_name = (proposal.after or proposal.before or {}).get("name", "medication")
        await self.audit.log_event(
            elder_id=proposal.elder_id,
            circle_id=proposal.circle_id,
            actor=elder_name,
            action="proposal.reject",
            target=med_name,
            details={
                "proposal_id": proposal.id,
                "medication_name": med_name,
                "action": proposal.action,
                "rejection_reason": proposal.rejection_reason,
            },
        )
        return updated

    async def get_pending_proposals(self, circle_id: str) -> list[ChangeProposal]:
        """Fetch all pending proposals for a circle, newest first."""
        proposals = await self.repos.proposals.find(
            lambda p: p.circle_id == circle_id and p.status == ProposalStatus.PENDING
        )
        return sorted(proposals, key=lambda p: p.created_at, reverse=True)

    async def get_emergency_proposals(self, circle_id: str, limit: int = 5) -> list[ChangeProposal]:
        """Fetch recent emergency proposals for prominent display."""
        proposals = await self.repos.proposals.find(
            lambda p: p.circle_id == circle_id and p.is_emergency
        )
        sorted_proposals = sorted(proposals, key=lambda p: p.created_at, reverse=True)
        return sorted_proposals[:limit]

    async def _apply_delete(self, before: dict[str, Any] | None) -> None:
        """Delete medication and associated schedules from repositories."""
        if before and "id" in before:
            med_id = before["id"]
            await self.repos.medications.delete(med_id)
            schedules = await self.repos.schedules.find(lambda s: s.medication_id == med_id)
            for s in schedules:
                await self.repos.schedules.delete(s.id)

    async def _apply_add(self, circle_id: str, after: dict[str, Any]) -> Medication:
        """Create and save new medication and its schedule."""
        med_id = after.get("id") or str(uuid4())
        sched_data = after.get("schedule") or {}
        schedule = DoseSchedule(
            id=sched_data.get("id") or str(uuid4()),
            medication_id=med_id,
            times_of_day=sched_data.get("times_of_day", ["08:00"]),
            days_of_week=sched_data.get("days_of_week", [0, 1, 2, 3, 4, 5, 6]),
            start_date=sched_data.get("start_date") or dt.datetime.now().date(),
            end_date=sched_data.get("end_date"),
            max_doses_per_day=sched_data.get("max_doses_per_day", 1),
            dose_amount=sched_data.get("dose_amount", "1 tablet"),
        )
        med = Medication(
            id=med_id,
            circle_id=circle_id,
            name=after.get("name", "Medication"),
            dosage=after.get("dosage", "1 tablet"),
            instructions=after.get("instructions", ""),
            prescribing_doctor=after.get("prescribing_doctor", ""),
            schedule=schedule,
        )
        await self.repos.schedules.save(schedule.id, schedule)
        await self.repos.medications.save(med.id, med)
        return med

    async def _apply_edit(
        self, before: dict[str, Any] | None, after: dict[str, Any]
    ) -> Medication:
        """Update existing medication and its schedule in repositories."""
        med_id = after.get("id") or (before or {}).get("id")
        if not med_id:
            raise ValueError("Cannot edit medication without medication ID.")
        existing = await self.repos.medications.get(med_id)
        if not existing:
            raise ValueError(f"Medication '{med_id}' not found to edit.")

        existing.name = after.get("name", existing.name)
        existing.dosage = after.get("dosage", existing.dosage)
        existing.instructions = after.get("instructions", existing.instructions)
        existing.prescribing_doctor = after.get("prescribing_doctor", existing.prescribing_doctor)

        if "schedule" in after and isinstance(after["schedule"], dict):
            sched_data = after["schedule"]
            existing_sched = existing.schedule or DoseSchedule(medication_id=med_id)
            existing_sched.times_of_day = sched_data.get(
                "times_of_day", existing_sched.times_of_day
            )
            existing_sched.days_of_week = sched_data.get(
                "days_of_week", existing_sched.days_of_week
            )
            existing_sched.max_doses_per_day = sched_data.get(
                "max_doses_per_day", existing_sched.max_doses_per_day
            )
            existing_sched.dose_amount = sched_data.get(
                "dose_amount", existing_sched.dose_amount
            )
            existing.schedule = existing_sched
            await self.repos.schedules.save(existing_sched.id, existing_sched)

        await self.repos.medications.save(existing.id, existing)
        return existing

    async def _apply_change(
        self,
        circle_id: str,
        action: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> Medication | None:
        """Atomically apply the approved/emergency change to the repository."""
        if action == "delete" or after is None:
            await self._apply_delete(before)
            return None
        if action == "add":
            return await self._apply_add(circle_id, after)
        if action == "edit":
            return await self._apply_edit(before, after)
        return None
