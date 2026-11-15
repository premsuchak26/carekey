"""Authentication and key management routes."""

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.models import MemberRole
from app.repositories import RepositoryContainer
from app.routes.dependencies import (
    AuthenticatedContext,
    get_auth_service,
    get_repos,
    get_session_manager,
    require_elder,
    verify_csrf,
)
from app.services.auth import AuthError, AuthService
from app.services.session import SessionManager

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["Authentication"])


@router.get("/circle/create", response_class=HTMLResponse)
async def create_circle_page(request: Request) -> HTMLResponse:
    """Render create care circle page."""
    return templates.TemplateResponse(request=request, name="create_circle.html")


@router.post("/circle/create", response_class=HTMLResponse)
async def create_circle_action(
    request: Request,
    elder_name: Annotated[str, Form()],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    elder_email: Annotated[str, Form()] = "elder@carekey.local",
    circle_name: Annotated[str | None, Form()] = None,
    timezone: Annotated[str, Form()] = "Asia/Kolkata",
) -> HTMLResponse:
    """Create a new circle with required email and timezone, displaying the owner passcode once."""
    if not elder_name.strip():
        return templates.TemplateResponse(
            request=request,
            name="create_circle.html",
            context={
                "error": "Elder name is required.",
                "elder_name": elder_name,
                "elder_email": elder_email,
                "timezone": timezone,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        circle, elder, owner_passcode = await auth_service.create_circle(
            elder_name=elder_name.strip(),
            elder_email=elder_email.strip(),
            circle_name=circle_name.strip() if circle_name else None,
            timezone=timezone.strip(),
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            request=request,
            name="create_circle.html",
            context={
                "error": str(exc),
                "elder_name": elder_name,
                "elder_email": elder_email,
                "timezone": timezone,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return templates.TemplateResponse(
        request=request,
        name="circle_created.html",
        context={
            "circle": circle,
            "elder": elder,
            "owner_passcode": owner_passcode,
            "success": "Care Circle successfully created! Please save your passcode now.",
        },
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    circle_code: str | None = None,
) -> HTMLResponse:
    """Render circle login page."""
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"circle_code": circle_code or ""},
    )


@router.post("/login", response_class=HTMLResponse)
async def login_action(
    request: Request,
    circle_code: Annotated[str, Form()],
    passcode: Annotated[str, Form()],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> Response:
    """Authenticate member, set session cookie, and redirect to appropriate screen."""
    client_ip = request.client.host if request.client else "127.0.0.1"

    try:
        circle, member = await auth_service.login(
            circle_code=circle_code,
            passcode=passcode,
            client_ip=client_ip,
        )
    except AuthError as exc:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "circle_code": circle_code,
                "error": exc.message,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    target_path = "/today" if member.role == MemberRole.ELDER else "/dashboard"
    response = RedirectResponse(url=target_path, status_code=status.HTTP_303_SEE_OTHER)

    session_manager.set_session_cookie(
        response=response,
        circle_id=circle.id,
        member_id=member.id,
        role=member.role.value,
        member_name=member.name,
    )
    return response


@router.post("/logout")
async def logout(
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> RedirectResponse:
    """Clear session cookie and redirect to login."""
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    session_manager.clear_session_cookie(response)
    return response


@router.get("/keys", response_class=HTMLResponse)
async def manage_keys_page(
    request: Request,
    ctx: Annotated[AuthenticatedContext, Depends(require_elder)],
    repos: Annotated[RepositoryContainer, Depends(get_repos)],
) -> HTMLResponse:
    """Render key management interface for Elder circle owner."""
    members = await repos.members.find(lambda m: m.circle_id == ctx.circle.id)
    return templates.TemplateResponse(
        request=request,
        name="keys.html",
        context={
            "ctx": ctx,
            "members": members,
            "now": datetime.now(),
        },
    )


@router.post("/keys/issue", response_class=HTMLResponse)
async def issue_key_action(
    request: Request,
    name: Annotated[str, Form()],
    role: Annotated[str, Form()],
    ctx: Annotated[AuthenticatedContext, Depends(require_elder)],
    _csrf: Annotated[None, Depends(verify_csrf)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    repos: Annotated[RepositoryContainer, Depends(get_repos)],
    email: Annotated[str, Form()] = "member@carekey.local",
    validity_days: Annotated[int, Form()] = 30,
) -> HTMLResponse:
    """Issue a new random 12-character member key with required validated email."""
    try:
        member_role = MemberRole(role)
    except ValueError:
        member_role = MemberRole.HELPER

    try:
        new_member, new_passcode = await auth_service.issue_member_key(
            circle_id=ctx.circle.id,
            name=name.strip(),
            email=email.strip(),
            role=member_role,
            validity_days=validity_days,
        )
    except ValueError as exc:
        members = await repos.members.find(lambda m: m.circle_id == ctx.circle.id)
        return templates.TemplateResponse(
            request=request,
            name="keys.html",
            context={
                "ctx": ctx,
                "members": members,
                "now": datetime.now(),
                "error": str(exc),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    members = await repos.members.find(lambda m: m.circle_id == ctx.circle.id)

    return templates.TemplateResponse(
        request=request,
        name="keys.html",
        context={
            "ctx": ctx,
            "members": members,
            "new_member": new_member,
            "new_passcode": new_passcode,
            "now": datetime.now(),
            "success": f"New access key issued for {new_member.name}!",
        },
    )


@router.post("/keys/revoke")
async def revoke_key_action(
    member_id: Annotated[str, Form()],
    ctx: Annotated[AuthenticatedContext, Depends(require_elder)],
    _csrf: Annotated[None, Depends(verify_csrf)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> RedirectResponse:
    """Revoke an existing member key instantly."""
    await auth_service.revoke_member_key(circle_id=ctx.circle.id, member_id=member_id)
    return RedirectResponse(url="/keys", status_code=status.HTTP_303_SEE_OTHER)
