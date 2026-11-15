"""Health check service for verifying platform and subsystem availability.

Encapsulates application diagnostic logic so routes remain purely transport-focused.
"""

from typing import Any

from app.config import Settings


class HealthService:
    """Service responsible for aggregating system health indicators."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the health service.

        Args:
            settings: Current application runtime configuration.
        """
        self.settings = settings

    async def get_health_status(self) -> dict[str, Any]:
        """Aggregate health status of the application and its subsystems.

        Returns:
            Dictionary containing overall health status, environment, and repository mode.
        """
        return {
            "status": "ok",
            "app": self.settings.app_name,
            "environment": self.settings.environment,
            "repository_backend": self.settings.repository_backend,
            "repository_type": self.settings.repository_backend,
        }
