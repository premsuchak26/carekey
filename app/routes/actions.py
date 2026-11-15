"""Routes for single-use, expiring one-tap email actions."""

import hashlib
import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import Settings, get_settings
from app.repositories import RepositoryContainer
from app.routes.dependencies import (
    get_action_token_manager,
    get_audit_service,
    get_email_sender,
    get_medication_service,
    get_repos,
)
from app.services.action_tokens import ActionTokenManager
from app.services.audit import AuditService
from app.services.email import EmailSenderProtocol
from app.services.medication import MedicationService

router = APIRouter(prefix="/actions", tags=["actions"])
templates = Jinja2Templates(directory="app/templates")


def compute_action_csrf(secret_key: str, token: str) -> str:
    """Generate CSRF token bound to action token and secret key."""
    return hmac.new(
        secret_key.encode("utf-8"),
        f"action_csrf:{token}".encode(),
        hashlib.sha256,
    ).hexdigest()


@router.get("/confirm", response_class=HTMLResponse)
async def confirm_action_page(
    request: Request,
    token: str,
    settings: Annotated[Settings, Depends(get_settings)],
    token_manager: Annotated[ActionTokenManager, Depends(get_action_token_manager)],
    repos: Annotated[RepositoryContainer, Depends(get_repos)],
) -> Any:
    """Render high-contrast confirmation page for one-tap action link."""
    payload = await token_manager.verify_token(token)
    if not payload:
        return templates.TemplateResponse(
            request=request,
            name="base.html",
            context={
                "request": request,
                "error": "This action link is invalid, has expired, or has already been used.",
            },
            status_code=400,
        )

    med = await repos.medications.get(payload.medication_id)
    med_name = med.name if med else "Medication"
    dosage = med.dosage if med else ""

    csrf_token = compute_action_csrf(settings.secret_key, token)

    if payload.action in ("took_it", "taken"):
        action_title = "Confirm You Took Your Medication"
        description = f"Please confirm that you took your scheduled dose of {med_name}."
        button_text = "Yes, I Took It"
        button_class = "btn-success"
    elif payload.action == "snooze":
        action_title = "Snooze Reminder"
        description = f"We will pause and remind you again in 15 minutes for your {med_name} dose."
        button_text = "Yes, Snooze 15 Min"
        button_class = "btn-primary"
    elif payload.action == "call_me":
        action_title = "Request a Phone Call"
        description = "We will immediately alert your care circle helpers to give you a call."
        button_text = "Yes, Please Call Me"
        button_class = "btn-danger"
    else:
        action_title = "Confirm Action"
        description = "Please confirm this action."
        button_text = "Confirm"
        button_class = "btn-primary"

    return templates.TemplateResponse(
        request=request,
        name="action_confirm.html",
        context={
            "request": request,
            "token": token,
            "csrf_token": csrf_token,
            "action_title": action_title,
            "description": description,
            "button_text": button_text,
            "button_class": button_class,
            "medication_name": med_name,
            "dosage": dosage,
            "scheduled_time": payload.scheduled_time,
        },
    )


@router.post("/execute", response_class=HTMLResponse)
async def execute_action(
    request: Request,
    token: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    settings: Annotated[Settings, Depends(get_settings)],
    token_manager: Annotated[ActionTokenManager, Depends(get_action_token_manager)],
    med_service: Annotated[MedicationService, Depends(get_medication_service)],
    email_sender: Annotated[EmailSenderProtocol, Depends(get_email_sender)],
    audit_service: Annotated[AuditService, Depends(get_audit_service)],
) -> Any:
    """Validate CSRF, verify and consume token, and execute action."""
    expected_csrf = compute_action_csrf(settings.secret_key, token)
    if not hmac.compare_digest(csrf_token, expected_csrf):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired CSRF token.",
        )

    payload = await token_manager.verify_token(token)
    if not payload:
        return templates.TemplateResponse(
            request=request,
            name="base.html",
            context={
                "request": request,
                "error": "This action link is invalid, has expired, or has already been used.",
            },
            status_code=400,
        )

    result = await token_manager.execute_action(
        payload=payload,
        medication_service=med_service,
        email_sender=email_sender,
        audit_service=audit_service,
    )

    return templates.TemplateResponse(
        request=request,
        name="action_success.html",
        context={
            "request": request,
            "message": result.get("status", "Action completed successfully."),
        },
    )
