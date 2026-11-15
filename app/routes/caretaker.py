"""Caretaker dashboard and landing routes."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.routes.dependencies import (
    AuthenticatedContext,
    get_appointment_service,
    get_current_context,
    get_medication_service,
    get_session_manager,
)
from app.services.appointment import AppointmentService
from app.services.medication import MedicationService
from app.services.session import SessionManager

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["Dashboard"])


@router.get("/")
async def root_entry(
    request: Request,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> RedirectResponse:
    """Redirect logged in users to today/dashboard, or new visitors to circle creation."""
    session = session_manager.get_session(request)
    if session:
        return RedirectResponse(url="/today")
    return RedirectResponse(url="/circle/create")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_screen(
    request: Request,
    ctx: Annotated[AuthenticatedContext, Depends(get_current_context)],
    med_service: Annotated[MedicationService, Depends(get_medication_service)],
    appt_service: Annotated[AppointmentService, Depends(get_appointment_service)],
) -> HTMLResponse:
    """Render Caretaker dashboard with metrics, compliance streak, and appointments."""
    today_doses = await med_service.get_today_doses(circle_id=ctx.circle.id)
    taken_count = sum(1 for d in today_doses if d["logged"] and d["status"] == "taken")

    medications = await med_service.list_medications(circle_id=ctx.circle.id)
    adherence_summaries = await med_service.get_adherence_summary(circle_id=ctx.circle.id)
    overall_streak = await med_service.get_overall_streak(circle_id=ctx.circle.id)
    appointments = await appt_service.list_appointments(
        circle_id=ctx.circle.id, upcoming_only=True
    )

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "ctx": ctx,
            "taken_today": taken_count,
            "total_today": len(today_doses),
            "medications": medications,
            "adherence_summaries": adherence_summaries,
            "overall_streak": overall_streak,
            "appointments": appointments,
        },
    )
