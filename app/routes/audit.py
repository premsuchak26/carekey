"""Routes for viewing and cryptographically verifying the tamper-evident health data audit log."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.routes.dependencies import (
    AuthenticatedContext,
    get_audit_service,
    get_current_context,
    verify_csrf,
)
from app.services.audit import AuditService

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/history", tags=["Audit Log"])


@router.get("", response_class=HTMLResponse)
async def view_history(
    request: Request,
    ctx: Annotated[AuthenticatedContext, Depends(get_current_context)],
    audit_service: Annotated[AuditService, Depends(get_audit_service)],
    actor: str | None = None,
) -> HTMLResponse:
    """Elder and care circle page: 'Who touched my health data'.

    Displays plain-language descriptions, newest first, with actor filtering
    and tamper-evident verification.
    """
    entries = await audit_service.get_entries(circle_id=ctx.circle.id, actor_filter=actor)
    actors = await audit_service.get_all_actors(circle_id=ctx.circle.id)

    formatted_entries = [
        {
            "entry": e,
            "sentence": audit_service.format_sentence(e),
            "timestamp": e.timestamp.strftime("%b %d, %Y at %I:%M %p"),
            "hash_short": e.hash[:12] + "...",
            "prev_hash_short": e.prev_hash[:12] + "...",
        }
        for e in entries
    ]

    return templates.TemplateResponse(
        request=request,
        name="audit_history.html",
        context={
            "ctx": ctx,
            "entries": formatted_entries,
            "actors": actors,
            "selected_actor": actor or "",
            "verification_status": None,
        },
    )


@router.post("/verify", response_class=HTMLResponse)
async def verify_history(
    request: Request,
    ctx: Annotated[AuthenticatedContext, Depends(get_current_context)],
    _csrf: Annotated[None, Depends(verify_csrf)],
    audit_service: Annotated[AuditService, Depends(get_audit_service)],
    actor: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    """Verify cryptographic chain of all audit entries and render verification badge."""
    is_valid, message = await audit_service.verify_circle_chain(circle_id=ctx.circle.id)

    entries = await audit_service.get_entries(circle_id=ctx.circle.id, actor_filter=actor)
    actors = await audit_service.get_all_actors(circle_id=ctx.circle.id)

    formatted_entries = [
        {
            "entry": e,
            "sentence": audit_service.format_sentence(e),
            "timestamp": e.timestamp.strftime("%b %d, %Y at %I:%M %p"),
            "hash_short": e.hash[:12] + "...",
            "prev_hash_short": e.prev_hash[:12] + "...",
        }
        for e in entries
    ]

    return templates.TemplateResponse(
        request=request,
        name="audit_history.html",
        context={
            "ctx": ctx,
            "entries": formatted_entries,
            "actors": actors,
            "selected_actor": actor or "",
            "verification_status": {
                "valid": is_valid,
                "message": message,
            },
        },
    )
