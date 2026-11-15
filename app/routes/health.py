"""Health check route definitions.

Provides liveness and readiness probe endpoints for monitoring and orchestration.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status

from app.config import Settings, get_settings
from app.services.health import HealthService

router = APIRouter(tags=["Health"])


def get_health_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthService:
    """Dependency provider for HealthService.

    Args:
        settings: Application settings injected via FastAPI dependency.

    Returns:
        Instantiated HealthService instance.
    """
    return HealthService(settings=settings)


@router.get(
    "/healthz",
    status_code=status.HTTP_200_OK,
    summary="Application Health Probe",
    description="Endpoint for container probes, uptime monitoring, and smoke testing.",
    response_model=dict[str, Any],
)
async def healthz(
    service: Annotated[HealthService, Depends(get_health_service)],
) -> dict[str, Any]:
    """Return application health status.

    Args:
        service: Injected health service instance.

    Returns:
        Dictionary reflecting the current health status and basic platform metrics.
    """
    return await service.get_health_status()
