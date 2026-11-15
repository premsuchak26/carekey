"""Base repository interface and generic protocol definitions.

Defines the contract that both Firestore and In-Memory storage adapters implement.
"""

from typing import Protocol, TypeVar

T = TypeVar("T")


class RepositoryProtocol(Protocol[T]):
    """Generic repository protocol for persistent entity storage and retrieval."""

    async def get(self, entity_id: str) -> T | None:
        """Retrieve an entity by its unique identifier.

        Args:
            entity_id: The unique identifier of the entity.

        Returns:
            The entity if found, None otherwise.
        """
        ...

    async def list_all(self, limit: int = 100) -> list[T]:
        """List all entities up to the specified limit.

        Args:
            limit: Maximum number of entities to return.

        Returns:
            List of retrieved entities.
        """
        ...

    async def save(self, entity_id: str, data: T) -> None:
        """Create or update an entity.

        Args:
            entity_id: The unique identifier of the entity.
            data: The entity data to store.
        """
        ...

    async def delete(self, entity_id: str) -> bool:
        """Delete an entity by its identifier.

        Args:
            entity_id: The unique identifier of the entity to delete.

        Returns:
            True if the entity existed and was deleted, False otherwise.
        """
        ...


class HealthCheckableRepository(Protocol):
    """Protocol for repositories capable of verifying storage connectivity."""

    async def ping(self) -> bool:
        """Verify repository storage health.

        Returns:
            True if storage backend is reachable and responsive, False otherwise.
        """
        ...
