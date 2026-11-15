"""In-memory repository implementation for automated testing and local prototyping.

Provides an isolated, fast dictionary-backed store satisfying RepositoryProtocol.
"""

from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class InMemoryRepository[T]:
    """Thread-safe in-memory key-value repository for testing and development."""

    def __init__(self) -> None:
        """Initialize empty storage state."""
        self._storage: dict[str, T] = {}

    async def get(self, entity_id: str) -> T | None:
        """Retrieve an entity by its identifier."""
        return self._storage.get(entity_id)

    async def list_all(self, limit: int = 100) -> list[T]:
        """List entities stored in memory up to limit."""
        return list(self._storage.values())[:limit]

    async def find(self, predicate: Callable[[T], bool]) -> list[T]:
        """Return all entities satisfying the predicate function."""
        return [item for item in self._storage.values() if predicate(item)]

    async def save(self, entity_id: str, data: T) -> None:
        """Persist or overwrite an entity in memory."""
        self._storage[entity_id] = data

    async def delete(self, entity_id: str) -> bool:
        """Remove an entity from memory."""
        if entity_id in self._storage:
            del self._storage[entity_id]
            return True
        return False

    async def ping(self) -> bool:
        """Check availability of in-memory store."""
        return True

    def clear(self) -> None:
        """Reset storage state between tests."""
        self._storage.clear()
