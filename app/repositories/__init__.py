"""Repository package containing data access abstractions and implementations."""

from typing import Any

from app.config import Settings, get_settings
from app.repositories.base import HealthCheckableRepository, RepositoryProtocol
from app.repositories.firestore import FirestoreRepository
from app.repositories.in_memory import InMemoryRepository


def get_repository[T](
    collection_name: str, settings: Settings | None = None
) -> RepositoryProtocol[T] | Any:
    """Instantiate the configured repository backend lazily.

    Creates FirestoreRepository only when repository_backend is set to 'firestore'.
    Defaults to InMemoryRepository otherwise.

    Args:
        collection_name: Target collection or entity table name.
        settings: Application settings instance; resolved via get_settings() if omitted.

    Returns:
        Configured repository satisfying RepositoryProtocol.
    """
    if settings is None:
        settings = get_settings()

    if settings.repository_backend == "firestore":
        return FirestoreRepository[T](collection_name=collection_name, settings=settings)

    return InMemoryRepository[T]()


__all__ = [
    "FirestoreRepository",
    "HealthCheckableRepository",
    "InMemoryRepository",
    "RepositoryProtocol",
    "get_repository",
]
