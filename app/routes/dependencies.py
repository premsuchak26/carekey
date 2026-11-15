"""FastAPI route dependencies for authentication, role gating, and CSRF protection."""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, get_settings
from app.models import CareCircle, Member, MemberRole
from app.repositories import RepositoryContainer, get_repository_container
from app.services.appointment import AppointmentService
from app.services.audit import AuditService
from app.services.auth import AuthService
from app.services.medication import MedicationService
from app.services.proposals import ProposalService
from app.services.session import SessionManager


def get_repos(
    settings: Annotated[Settings, Depends(get_settings)],
) -> RepositoryContainer:
    """Dependency provider for RepositoryContainer."""
    return get_repository_container(settings=settings)


def get_audit_service(
    repos: Annotated[RepositoryContainer, Depends(get_repos)],
) -> AuditService:
    """Dependency provider for AuditService."""
    return AuditService(repositories=repos)


def get_auth_service(
    repos: Annotated[RepositoryContainer, Depends(get_repos)],
    settings: Annotated[Settings, Depends(get_settings)],
    audit: Annotated[AuditService, Depends(get_audit_service)],
) -> AuthService:
    """Dependency provider for AuthService."""
    return AuthService(repositories=repos, settings=settings, audit_service=audit)


def get_session_manager(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionManager:
    """Dependency provider for SessionManager."""
    return SessionManager(settings=settings)


def get_medication_service(
    repos: Annotated[RepositoryContainer, Depends(get_repos)],
    audit: Annotated[AuditService, Depends(get_audit_service)],
) -> MedicationService:
    """Dependency provider for MedicationService."""
    return MedicationService(repositories=repos, audit_service=audit)


def get_proposal_service(
    repos: Annotated[RepositoryContainer, Depends(get_repos)],
    audit: Annotated[AuditService, Depends(get_audit_service)],
) -> ProposalService:
    """Dependency provider for ProposalService."""
    return ProposalService(repositories=repos, audit_service=audit)


def get_appointment_service(
    repos: Annotated[RepositoryContainer, Depends(get_repos)],
) -> AppointmentService:
    """Dependency provider for AppointmentService."""
    return AppointmentService(repositories=repos)


class AuthenticatedContext:
    """Encapsulates authenticated circle and member context."""

    def __init__(self, circle: CareCircle, member: Member, csrf_token: str) -> None:
        self.circle = circle
        self.member = member
        self.csrf_token = csrf_token


async def get_current_context(
    request: Request,
    repos: Annotated[RepositoryContainer, Depends(get_repos)],
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> AuthenticatedContext:
    """Extract authenticated session or raise 401."""
    session = session_manager.get_session(request)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"Location": "/login"},
        )

    circle_id = session.get("circle_id", "")
    member_id = session.get("member_id", "")

    circle = await repos.circles.get(circle_id)
    member = await repos.members.get(member_id)

    if not circle or not member or member.circle_id != circle.id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalid or circle not found.",
        )

    if member.revoked_at:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access key has been revoked.",
        )

    csrf_token = session_manager.generate_csrf_token(member.id)
    return AuthenticatedContext(circle=circle, member=member, csrf_token=csrf_token)


def require_role(min_role: MemberRole) -> Callable[..., Any]:
    """Dependency factory enforcing minimum required role in role hierarchy."""

    async def _role_checker(
        ctx: Annotated[AuthenticatedContext, Depends(get_current_context)],
    ) -> AuthenticatedContext:
        if ctx.member.role.level < min_role.level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Insufficient permissions. Requires {min_role.value} or higher "
                    f"(your role: {ctx.member.role.value})."
                ),
            )
        return ctx

    return _role_checker


require_elder = require_role(MemberRole.ELDER)
require_manager = require_role(MemberRole.MANAGER)
require_helper = require_role(MemberRole.HELPER)
require_viewer = require_role(MemberRole.VIEWER)


async def verify_csrf(
    request: Request,
    ctx: Annotated[AuthenticatedContext, Depends(get_current_context)],
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> None:
    """Verify CSRF token for state-changing HTTP methods."""
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        token: str | None = request.headers.get("X-CSRF-Token")
        if not token:
            try:
                form = await request.form()
                token_val = form.get("csrf_token")
                token = str(token_val) if token_val is not None else None
            except Exception:
                token = None

        if not session_manager.validate_csrf_token(ctx.member.id, token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or missing CSRF token.",
            )
