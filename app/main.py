"""CareKey application entrypoint and ASGI setup."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.routes.health import router as health_router

BASE_DIR = Path(__file__).resolve().parent


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application instance.

    Args:
        settings: Optional custom settings instance for testing overrides.

    Returns:
        Configured FastAPI application instance.
    """
    if settings is None:
        settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        description=(
            "Elderly care and medication management platform with two-key rule, "
            "scoped revocable access, and tamper-evident audit logging."
        ),
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Override settings dependency if custom settings are provided
    application.dependency_overrides[get_settings] = lambda: settings
    application.state.settings = settings

    # Static assets mounting
    static_path = BASE_DIR / "static"
    if static_path.exists():
        application.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    # Register routers
    application.include_router(health_router)

    return application


app = create_app()
