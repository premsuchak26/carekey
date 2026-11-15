"""Internal stateless maintenance endpoints."""

import datetime as dt
import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.config import Settings, get_settings
from app.routes.dependencies import get_reminder_service
from app.services.reminders import ReminderService

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/tick")
async def process_tick(
    settings: Annotated[Settings, Depends(get_settings)],
    reminder_service: Annotated[ReminderService, Depends(get_reminder_service)],
    x_internal_secret: Annotated[str | None, Header(alias="X-Internal-Secret")] = None,
    x_tick_secret: Annotated[str | None, Header(alias="X-Tick-Secret")] = None,
    now: Annotated[
        str | None, Query(description="Optional ISO timestamp for simulation/testing")
    ] = None,
) -> dict[str, Any]:
    """Execute stateless reminder evaluation tick.

    Protected by secret header compared in constant time against settings.tick_secret.
    """
    secret = x_internal_secret or x_tick_secret
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required internal secret header.",
        )

    if not hmac.compare_digest(secret, settings.tick_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal secret.",
        )

    parsed_now: dt.datetime | None = None
    if now:
        try:
            # Handle URL-decoded '+' as space in timezone offsets
            clean_now = now.replace(" ", "+") if " " in now and "+" not in now else now
            parsed_now = dt.datetime.fromisoformat(clean_now)
        except ValueError:
            parsed_now = None

    return await reminder_service.process_tick(now=parsed_now)
