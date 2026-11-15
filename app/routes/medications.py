"""Medication and dose scheduling routes."""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.routes.dependencies import (
    AuthenticatedContext,
    get_current_context,
    get_medication_service,
    require_helper,
    require_manager,
    verify_csrf,
)
from app.services.medication import MedicationService

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
    times_of_day: Annotated[str, Form()] = "08:00",
    dose_amount: Annotated[str, Form()] = "1 tablet",
    instructions: Annotated[str, Form()] = "",
    prescribing_doctor: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Add a new medication and schedule (Elder and MANAGER only)."""
    times_list = [t.strip() for t in times_of_day.split(",") if t.strip()]
    if not times_list:
        times_list = ["08:00"]

    await med_service.add_medication(
        circle_id=ctx.circle.id,
        name=name.strip(),
        dosage=dosage.strip(),
        instructions=instructions.strip(),
        prescribing_doctor=prescribing_doctor.strip(),
        times_of_day=times_list,
        dose_amount=dose_amount.strip(),
    )
    return RedirectResponse(url="/medications", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/delete")
async def delete_medication_action(
    medication_id: Annotated[str, Form()],
    ctx: Annotated[AuthenticatedContext, Depends(require_manager)],
    _csrf: Annotated[None, Depends(verify_csrf)],
    med_service: Annotated[MedicationService, Depends(get_medication_service)],
) -> RedirectResponse:
    """Delete a medication (Elder and MANAGER only)."""
    await med_service.delete_medication(circle_id=ctx.circle.id, medication_id=medication_id)
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
