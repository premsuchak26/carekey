"""Medication and dose scheduling routes."""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.models import MemberRole
from app.routes.dependencies import (
    AuthenticatedContext,
    get_current_context,
    get_medication_service,
    get_proposal_service,
    require_helper,
    require_manager,
    verify_csrf,
)
from app.services.medication import MedicationService
from app.services.proposals import ProposalService

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/medications", tags=["Medications"])


@router.get("", response_class=HTMLResponse)
async def list_medications_screen(
    request: Request,
    ctx: Annotated[AuthenticatedContext, Depends(get_current_context)],
    med_service: Annotated[MedicationService, Depends(get_medication_service)],
) -> HTMLResponse:
    """Render list of medications and schedules for the care circle."""
    medications = await med_service.list_medications(circle_id=ctx.circle.id)
    return templates.TemplateResponse(
        request=request,
        name="medications.html",
        context={
            "ctx": ctx,
            "medications": medications,
        },
    )


@router.post("/add")
async def add_medication_action(
    name: Annotated[str, Form()],
    dosage: Annotated[str, Form()],
    ctx: Annotated[AuthenticatedContext, Depends(require_manager)],
    _csrf: Annotated[None, Depends(verify_csrf)],
    med_service: Annotated[MedicationService, Depends(get_medication_service)],
    proposal_service: Annotated[ProposalService, Depends(get_proposal_service)],
    times_of_day: Annotated[str, Form()] = "08:00",
    dose_amount: Annotated[str, Form()] = "1 tablet",
    instructions: Annotated[str, Form()] = "",
    prescribing_doctor: Annotated[str, Form()] = "",
    reason: Annotated[str, Form()] = "",
    is_emergency: Annotated[bool, Form()] = False,
    emergency_reason: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Add a new medication and schedule (Elder direct, MANAGER via proposal or emergency)."""
    times_list = [t.strip() for t in times_of_day.split(",") if t.strip()]
    if not times_list:
        times_list = ["08:00"]

    after_payload = {
        "name": name.strip(),
        "dosage": dosage.strip(),
        "instructions": instructions.strip(),
        "prescribing_doctor": prescribing_doctor.strip(),
        "schedule": {
            "times_of_day": times_list,
            "days_of_week": [0, 1, 2, 3, 4, 5, 6],
            "dose_amount": dose_amount.strip(),
            "max_doses_per_day": len(times_list),
        },
    }

    is_elder = ctx.member.role == MemberRole.ELDER

    if is_elder:
        await med_service.add_medication(
            circle_id=ctx.circle.id,
            name=name.strip(),
            dosage=dosage.strip(),
            instructions=instructions.strip(),
            prescribing_doctor=prescribing_doctor.strip(),
            times_of_day=times_list,
            dose_amount=dose_amount.strip(),
            actor_name=ctx.member.name,
        )
        return RedirectResponse(
            url="/medications?msg=Medication+added", status_code=status.HTTP_303_SEE_OTHER
        )

    # Non-elder MANAGER: Emergency override or Two-Key Proposal
    if is_emergency:
        if not emergency_reason.strip():
            return RedirectResponse(
                url="/medications?error=Emergency+override+requires+a+documented+reason",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        await proposal_service.emergency_override(
            circle_id=ctx.circle.id,
            elder_id=ctx.circle.elder_id,
            author_id=ctx.member.id,
            author_name=ctx.member.name,
            author_role=ctx.member.role.value,
            action="add",
            emergency_reason=emergency_reason.strip(),
            before=None,
            after=after_payload,
        )
        return RedirectResponse(
            url="/medications?msg=Emergency+override+applied+and+logged",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Two-Key rule proposal
    user_reason = reason.strip() or f"Proposal to add {name.strip()} by {ctx.member.name}"
    await proposal_service.create_proposal(
        circle_id=ctx.circle.id,
        elder_id=ctx.circle.elder_id,
        author_id=ctx.member.id,
        author_name=ctx.member.name,
        author_role=ctx.member.role.value,
        action="add",
        reason=user_reason,
        before=None,
        after=after_payload,
    )
    return RedirectResponse(
        url="/medications?msg=Proposal+submitted+for+Elder+approval+(Two-Key+Rule)",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/delete")
async def delete_medication_action(
    medication_id: Annotated[str, Form()],
    ctx: Annotated[AuthenticatedContext, Depends(require_manager)],
    _csrf: Annotated[None, Depends(verify_csrf)],
    med_service: Annotated[MedicationService, Depends(get_medication_service)],
    proposal_service: Annotated[ProposalService, Depends(get_proposal_service)],
    reason: Annotated[str, Form()] = "",
    is_emergency: Annotated[bool, Form()] = False,
    emergency_reason: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Delete a medication (Elder direct, MANAGER via proposal or emergency)."""
    med = await med_service.repos.medications.get(medication_id)
    if not med or med.circle_id != ctx.circle.id:
        return RedirectResponse(url="/medications", status_code=status.HTTP_303_SEE_OTHER)

    before_payload = med.model_dump()
    is_elder = ctx.member.role == MemberRole.ELDER

    if is_elder:
        await med_service.delete_medication(
            circle_id=ctx.circle.id, medication_id=medication_id, actor_name=ctx.member.name
        )
        return RedirectResponse(
            url="/medications?msg=Medication+deleted", status_code=status.HTTP_303_SEE_OTHER
        )

    if is_emergency:
        if not emergency_reason.strip():
            return RedirectResponse(
                url="/medications?error=Emergency+override+requires+a+documented+reason",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        await proposal_service.emergency_override(
            circle_id=ctx.circle.id,
            elder_id=ctx.circle.elder_id,
            author_id=ctx.member.id,
            author_name=ctx.member.name,
            author_role=ctx.member.role.value,
            action="delete",
            emergency_reason=emergency_reason.strip(),
            before=before_payload,
            after=None,
        )
        return RedirectResponse(
            url="/medications?msg=Emergency+override+deletion+applied",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    user_reason = reason.strip() or f"Proposal to remove {med.name} by {ctx.member.name}"
    await proposal_service.create_proposal(
        circle_id=ctx.circle.id,
        elder_id=ctx.circle.elder_id,
        author_id=ctx.member.id,
        author_name=ctx.member.name,
        author_role=ctx.member.role.value,
        action="delete",
        reason=user_reason,
        before=before_payload,
        after=None,
    )
    return RedirectResponse(
        url="/medications?msg=Removal+proposal+submitted+for+Elder+approval",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    return RedirectResponse(url="/medications", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/log-dose")
async def log_dose_action(
    medication_id: Annotated[str, Form()],
    action_status: Annotated[str, Form(alias="status")],
    ctx: Annotated[AuthenticatedContext, Depends(require_helper)],
    _csrf: Annotated[None, Depends(verify_csrf)],
    med_service: Annotated[MedicationService, Depends(get_medication_service)],
) -> RedirectResponse:
    """Log dose administration or skip (HELPER, MANAGER, or ELDER)."""
    dose_choice: Literal["taken", "skipped"] = "taken" if action_status == "taken" else "skipped"
    now = datetime.now()

    await med_service.log_dose(
        circle_id=ctx.circle.id,
        medication_id=medication_id,
        scheduled_time=now,
        status=dose_choice,
        logged_by=ctx.member.name,
        timestamp=now,
    )
    return RedirectResponse(url="/medications", status_code=status.HTTP_303_SEE_OTHER)
