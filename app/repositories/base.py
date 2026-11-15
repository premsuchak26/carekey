"""Base repository interface and generic protocol definitions.

Defines the contract that both Firestore and In-Memory storage adapters implement.
"""

from collections.abc import Callable
from typing import Protocol, TypeVar

T = TypeVar("T")


class RepositoryProtocol(Protocol[T]):
    """Generic repository protocol for persistent entity storage and retrieval."""

    async def get(self, entity_id: str) -> T | None:
        """Retrieve an entity by its unique identifier."""
        ...

    async def list_all(self, limit: int = 100) -> list[T]:
        """List all entities up to the specified limit."""
        ...

    async def find(self, predicate: Callable[[T], bool]) -> list[T]:
        """Filter entities matching predicate."""
        ...

    async def save(self, entity_id: str, data: T) -> None:
        """Create or update an entity."""
        ...

    async def delete(self, entity_id: str) -> bool:
        """Delete an entity by its identifier."""
        ...


class HealthCheckableRepository(Protocol):
    """Protocol for repositories capable of verifying storage connectivity."""

    async def ping(self) -> bool:
        """Verify repository storage health."""
        ...
