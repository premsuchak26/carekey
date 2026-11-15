"""Routes for managing Two-Key Rule medication change proposals."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.models import MemberRole
from app.routes.dependencies import (
    AuthenticatedContext,
    get_current_context,
    get_proposal_service,
    require_elder,
    verify_csrf,
)
from app.services.proposals import ProposalService

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/proposals", tags=["Proposals"])


@router.get("", response_class=HTMLResponse)
async def list_proposals(
    request: Request,
    ctx: Annotated[AuthenticatedContext, Depends(get_current_context)],
    proposal_service: Annotated[ProposalService, Depends(get_proposal_service)],
) -> HTMLResponse:
    """Render list of pending and recent change proposals."""
    pending = await proposal_service.get_pending_proposals(circle_id=ctx.circle.id)
    emergencies = await proposal_service.get_emergency_proposals(circle_id=ctx.circle.id)

    # All proposals for circle
    all_proposals = await proposal_service.repos.proposals.find(
        lambda p: p.circle_id == ctx.circle.id
    )
    sorted_history = sorted(
        [p for p in all_proposals if p.status != "PENDING"],
        key=lambda p: p.created_at,
        reverse=True,
    )

    is_elder = ctx.member.role == MemberRole.ELDER

    return templates.TemplateResponse(
        request=request,
        name="proposals.html",
        context={
            "ctx": ctx,
            "pending_proposals": pending,
            "emergency_proposals": emergencies,
            "proposal_history": sorted_history[:20],
            "is_elder": is_elder,
        },
    )


@router.post("/{proposal_id}/approve")
async def approve_proposal_route(
    proposal_id: str,
    ctx: Annotated[AuthenticatedContext, Depends(require_elder)],
    _csrf: Annotated[None, Depends(verify_csrf)],
    proposal_service: Annotated[ProposalService, Depends(get_proposal_service)],
) -> RedirectResponse:
    """Elder approves a pending change proposal; applies change atomically."""
    try:
        await proposal_service.approve_proposal(
            proposal_id=proposal_id,
            elder_id=ctx.member.id,
            elder_name=ctx.member.name,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to approve proposal: {exc}",
        ) from exc

    return RedirectResponse(
        url="/today?msg=Medication+change+approved+and+applied",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{proposal_id}/reject")
async def reject_proposal_route(
    proposal_id: str,
    ctx: Annotated[AuthenticatedContext, Depends(require_elder)],
    _csrf: Annotated[None, Depends(verify_csrf)],
    proposal_service: Annotated[ProposalService, Depends(get_proposal_service)],
    rejection_reason: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Elder rejects a pending change proposal with reason."""
    reason = rejection_reason.strip() or "Rejected by elder"
    try:
        await proposal_service.reject_proposal(
            proposal_id=proposal_id,
            elder_id=ctx.member.id,
            elder_name=ctx.member.name,
            rejection_reason=reason,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to reject proposal: {exc}",
        ) from exc

    return RedirectResponse(
        url="/today?msg=Medication+change+proposal+rejected",
        status_code=status.HTTP_303_SEE_OTHER,
    )
