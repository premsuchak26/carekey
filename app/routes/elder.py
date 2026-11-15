"""Elder-first simplified screens and one-click dose actions."""

from datetime import datetime, time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.routes.dependencies import (
    AuthenticatedContext,
    get_current_context,
    get_medication_service,
    require_helper,
    verify_csrf,
)
from app.services.medication import MedicationService

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["Elder Today"])


@router.get("/today", response_class=HTMLResponse)
async def today_screen(
    request: Request,
    ctx: Annotated[AuthenticatedContext, Depends(get_current_context)],
    med_service: Annotated[MedicationService, Depends(get_medication_service)],
) -> HTMLResponse:
    """Render high-contrast, large-button Today's Dose screen for elder or caretaker."""
    doses = await med_service.get_today_doses(circle_id=ctx.circle.id)
    today_str = datetime.now().strftime("%A, %B %d")

    return templates.TemplateResponse(
        request=request,
        name="today.html",
        context={
            "ctx": ctx,
            "doses": doses,
            "today_date_str": today_str,
        },
    )


@router.post("/today/dose/take")
async def take_dose_action(
    medication_id: Annotated[str, Form()],
    time_str: Annotated[str, Form()],
    ctx: Annotated[AuthenticatedContext, Depends(require_helper)],
    _csrf: Annotated[None, Depends(verify_csrf)],
    med_service: Annotated[MedicationService, Depends(get_medication_service)],
) -> RedirectResponse:
    """One-click dose confirmation from the Elder Today screen."""
    now = datetime.now()
    try:
        hour, minute = map(int, time_str.split(":"))
        scheduled_dt = datetime.combine(now.date(), time(hour, minute))
    except Exception:
        scheduled_dt = now

    await med_service.log_dose(
        circle_id=ctx.circle.id,
        medication_id=medication_id,
        scheduled_time=scheduled_dt,
        status="taken",
        logged_by=ctx.member.name,
        timestamp=now,
    )

    return RedirectResponse(url="/today", status_code=status.HTTP_303_SEE_OTHER)
