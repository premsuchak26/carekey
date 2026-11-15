"""Repository package containing data access abstractions and container."""

from typing import Any

from app.config import Settings, get_settings
from app.models import (
    Appointment,
    AuditEntry,
    CareCircle,
    ChangeProposal,
    DoseEvent,
    DoseSchedule,
    Elder,
    Medication,
    Member,
    ReminderSent,
    UsedActionToken,
)
from app.repositories.base import HealthCheckableRepository, RepositoryProtocol
from app.repositories.firestore import FirestoreRepository
from app.repositories.in_memory import InMemoryRepository


class RepositoryContainer:
    """Dependency container for all domain repositories."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        is_firestore = settings.repository_backend == "firestore"

        if is_firestore:
            self.elders: RepositoryProtocol[Elder] = FirestoreRepository("elders", settings)
            self.circles: RepositoryProtocol[CareCircle] = FirestoreRepository("circles", settings)
            self.members: RepositoryProtocol[Member] = FirestoreRepository("members", settings)
            self.medications: RepositoryProtocol[Medication] = FirestoreRepository(
                "medications", settings
            )
            self.schedules: RepositoryProtocol[DoseSchedule] = FirestoreRepository(
                "schedules", settings
            )
            self.dose_events: RepositoryProtocol[DoseEvent] = FirestoreRepository(
                "dose_events", settings
            )
            self.appointments: RepositoryProtocol[Appointment] = FirestoreRepository(
                "appointments", settings
            )
            self.proposals: RepositoryProtocol[ChangeProposal] = FirestoreRepository(
                "proposals", settings
            )
            self.audit_log: RepositoryProtocol[AuditEntry] = FirestoreRepository(
                "audit_entries", settings
            )
            self.reminders: RepositoryProtocol[ReminderSent] = FirestoreRepository(
                "reminders", settings
            )
            self.used_tokens: RepositoryProtocol[UsedActionToken] = FirestoreRepository(
                "used_tokens", settings
            )
        else:
            self.elders = InMemoryRepository[Elder]()
            self.circles = InMemoryRepository[CareCircle]()
            self.members = InMemoryRepository[Member]()
            self.medications = InMemoryRepository[Medication]()
            self.schedules = InMemoryRepository[DoseSchedule]()
            self.dose_events = InMemoryRepository[DoseEvent]()
            self.appointments = InMemoryRepository[Appointment]()
            self.proposals = InMemoryRepository[ChangeProposal]()
            self.audit_log = InMemoryRepository[AuditEntry]()
            self.reminders = InMemoryRepository[ReminderSent]()
            self.used_tokens = InMemoryRepository[UsedActionToken]()

    def clear(self) -> None:
        """Clear all in-memory repositories (used in testing)."""
        for repo in (
            self.elders,
            self.circles,
            self.members,
            self.medications,
            self.schedules,
            self.dose_events,
            self.appointments,
            self.proposals,
            self.audit_log,
            self.reminders,
            self.used_tokens,
        ):
            if isinstance(repo, InMemoryRepository):
                repo.clear()


_container_cache: dict[str, RepositoryContainer] = {}


def get_repository_container(settings: Settings | None = None) -> RepositoryContainer:
    """Return a cached RepositoryContainer instance."""
    if settings is None:
        settings = get_settings()
    key = f"{settings.repository_backend}:{settings.environment}"
    if key not in _container_cache:
        _container_cache[key] = RepositoryContainer(settings=settings)
    return _container_cache[key]


def reset_repository_container() -> None:
    """Clear all cached repository containers."""
    _container_cache.clear()


def get_repository[T](
    collection_name: str, settings: Settings | None = None
) -> RepositoryProtocol[T] | Any:
    """Instantiate a single configured repository backend lazily."""
    if settings is None:
        settings = get_settings()

    if settings.repository_backend == "firestore":
        return FirestoreRepository[T](collection_name=collection_name, settings=settings)

    return InMemoryRepository[T]()


__all__ = [
    "FirestoreRepository",
    "HealthCheckableRepository",
    "InMemoryRepository",
    "RepositoryContainer",
    "RepositoryProtocol",
    "get_repository",
    "get_repository_container",
    "reset_repository_container",
]
