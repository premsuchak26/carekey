"""In-memory repository implementation for automated testing and local prototyping.

Provides an isolated, fast dictionary-backed store satisfying RepositoryProtocol.
"""

from typing import TypeVar

T = TypeVar("T")


class InMemoryRepository[T]:
    """Thread-safe in-memory key-value repository for testing and development."""

    def __init__(self) -> None:
        """Initialize empty storage state."""
        self._storage: dict[str, T] = {}

    async def get(self, entity_id: str) -> T | None:
        """Retrieve an entity by its identifier.

        Args:
            entity_id: The unique identifier of the entity.

        Returns:
            The stored entity or None if absent.
        """
        return self._storage.get(entity_id)

    async def list_all(self, limit: int = 100) -> list[T]:
        """List entities stored in memory up to limit.

        Args:
            limit: Maximum count to return.

        Returns:
            List of stored entity items.
        """
        return list(self._storage.values())[:limit]

    async def save(self, entity_id: str, data: T) -> None:
        """Persist or overwrite an entity in memory.

        Args:
            entity_id: Unique identifier for keying.
            data: Entity data to store.
        """
        self._storage[entity_id] = data

    async def delete(self, entity_id: str) -> bool:
        """Remove an entity from memory.

        Args:
            entity_id: Unique identifier to remove.

        Returns:
            True if removed, False if key was not present.
        """
        if entity_id in self._storage:
            del self._storage[entity_id]
            return True
        return False

    async def ping(self) -> bool:
        """Check availability of in-memory store.

        Returns:
            True always since memory is available locally.
        """
        return True

    def clear(self) -> None:
        """Reset storage state between tests."""
        self._storage.clear()
