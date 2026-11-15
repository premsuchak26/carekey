"""Appointment scheduling and viewing routes."""

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.routes.dependencies import (
    AuthenticatedContext,
    get_appointment_service,
    get_current_context,
    require_manager,
    verify_csrf,
)
from app.services.appointment import AppointmentService

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/appointments", tags=["Appointments"])


@router.get("", response_class=HTMLResponse)
async def list_appointments_screen(
    request: Request,
    ctx: Annotated[AuthenticatedContext, Depends(get_current_context)],
    appt_service: Annotated[AppointmentService, Depends(get_appointment_service)],
) -> HTMLResponse:
    """Render appointments list and scheduling form."""
    appointments = await appt_service.list_appointments(circle_id=ctx.circle.id)
    return templates.TemplateResponse(
        request=request,
        name="appointments.html",
        context={
            "ctx": ctx,
            "appointments": appointments,
        },
    )


@router.post("/add")
async def add_appointment_action(
    doctor: Annotated[str, Form()],
    place: Annotated[str, Form()],
    datetime_str: Annotated[str, Form(alias="datetime")],
    ctx: Annotated[AuthenticatedContext, Depends(require_manager)],
    _csrf: Annotated[None, Depends(verify_csrf)],
    appt_service: Annotated[AppointmentService, Depends(get_appointment_service)],
    notes: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Schedule a new appointment (Elder and MANAGER only)."""
    try:
        appt_dt = datetime.fromisoformat(datetime_str)
    except Exception:
        appt_dt = datetime.now()

    await appt_service.add_appointment(
        circle_id=ctx.circle.id,
        doctor=doctor.strip(),
        place=place.strip(),
        appointment_datetime=appt_dt,
        notes=notes.strip(),
    )
    return RedirectResponse(url="/appointments", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/delete")
async def delete_appointment_action(
    appointment_id: Annotated[str, Form()],
    ctx: Annotated[AuthenticatedContext, Depends(require_manager)],
    _csrf: Annotated[None, Depends(verify_csrf)],
    appt_service: Annotated[AppointmentService, Depends(get_appointment_service)],
) -> RedirectResponse:
    """Delete an appointment (Elder and MANAGER only)."""
    await appt_service.delete_appointment(
        circle_id=ctx.circle.id, appointment_id=appointment_id
    )
    return RedirectResponse(url="/appointments", status_code=status.HTTP_303_SEE_OTHER)
