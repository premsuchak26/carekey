"""Routes package registering all application endpoints."""

from app.routes.appointments import router as appointments_router
from app.routes.audit import router as audit_router
from app.routes.auth import router as auth_router
from app.routes.caretaker import router as caretaker_router
from app.routes.elder import router as elder_router
from app.routes.health import router as health_router
from app.routes.medications import router as medications_router
from app.routes.proposals import router as proposals_router

__all__ = [
    "appointments_router",
    "audit_router",
    "auth_router",
    "caretaker_router",
    "elder_router",
    "health_router",
    "medications_router",
    "proposals_router",
]
