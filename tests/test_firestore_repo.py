"""Tests for FirestoreRepository adapter, typed serialization, and queries."""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.models import DoseSchedule, Elder, Medication
from app.repositories.firestore import FirestoreRepository
from scripts.seed_demo import seed_demo


class FakeDocSnapshot:
    """Mock Firestore DocumentSnapshot."""

    def __init__(self, doc_id: str, data: dict[str, Any] | None) -> None:
        self.id = doc_id
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return dict(self._data) if self._data is not None else None


class FakeDocRef:
    """Mock Firestore DocumentReference."""

    def __init__(self, doc_id: str, store: dict[str, dict[str, Any]]) -> None:
        self.doc_id = doc_id
        self.store = store

    async def get(self) -> FakeDocSnapshot:
        return FakeDocSnapshot(self.doc_id, self.store.get(self.doc_id))

    async def set(self, data: dict[str, Any]) -> None:
        self.store[self.doc_id] = dict(data)

    async def delete(self) -> None:
        self.store.pop(self.doc_id, None)


class FakeCollectionRef:
    """Mock Firestore CollectionReference."""

    def __init__(self, store: dict[str, dict[str, Any]]) -> None:
        self.store = store

    def document(self, doc_id: str) -> FakeDocRef:
        return FakeDocRef(doc_id, self.store)

    def limit(self, limit_num: int) -> "FakeCollectionRef":
        return self

    async def stream(self) -> AsyncIterator[FakeDocSnapshot]:
        for doc_id, data in list(self.store.items()):
            yield FakeDocSnapshot(doc_id, data)


class FakeAsyncClient:
    """Mock google.cloud.firestore.AsyncClient."""

    def __init__(self, project: str | None = None) -> None:
        self.project = project
        self.collections: dict[str, dict[str, dict[str, Any]]] = {}

    def collection(self, name: str) -> FakeCollectionRef:
        if name not in self.collections:
            self.collections[name] = {}
        return FakeCollectionRef(self.collections[name])


@pytest.fixture
def mock_firestore_settings() -> Settings:
    return Settings(
        app_name="CareKey-FirestoreTest",
        environment="test",
        repository_backend="firestore",
        firestore_project_id="test-gcp-project",
    )


@pytest.mark.asyncio
async def test_firestore_repository_crud_typed(mock_firestore_settings: Settings) -> None:
    """Verify FirestoreRepository saves, retrieves, and reconstructs typed Pydantic models."""
    repo = FirestoreRepository[Medication](
        collection_name="medications",
        settings=mock_firestore_settings,
        model_cls=Medication,
    )
    fake_client = FakeAsyncClient(project="test-gcp-project")
    repo._client = fake_client

    schedule = DoseSchedule(
        medication_id="med-1",
        times_of_day=["08:00", "20:00"],
        days_of_week=[0, 1, 2, 3, 4, 5, 6],
        max_doses_per_day=2,
    )
    med = Medication(
        id="med-1",
        circle_id="circle-100",
        name="Amlodipine",
        dosage="5mg",
        instructions="Take with water",
        schedule=schedule,
    )

    # 1. Save
    await repo.save(med.id, med)

    # 2. Get and verify typed deserialization
    fetched = await repo.get("med-1")
    assert fetched is not None
    assert isinstance(fetched, Medication)
    assert fetched.id == "med-1"
    assert fetched.name == "Amlodipine"
    assert fetched.dosage == "5mg"
    assert fetched.schedule is not None
    assert fetched.schedule.times_of_day == ["08:00", "20:00"]
    assert fetched.schedule.max_doses_per_day == 2

    # 3. Find with in-memory predicate
    matching = await repo.find(lambda m: m.circle_id == "circle-100")
    assert len(matching) == 1
    assert matching[0].name == "Amlodipine"

    non_matching = await repo.find(lambda m: m.circle_id == "circle-999")
    assert len(non_matching) == 0

    # 4. List all
    all_meds = await repo.list_all()
    assert len(all_meds) == 1

    # 5. Ping
    assert await repo.ping() is True

    # 6. Delete
    deleted = await repo.delete("med-1")
    assert deleted is True
    assert await repo.get("med-1") is None


@pytest.mark.asyncio
async def test_firestore_repository_lazy_client_project_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify project detection from settings or environment variable."""
    settings = Settings(
        app_name="CareKey-FirestoreTest",
        environment="test",
        repository_backend="firestore",
        firestore_project_id=None,
    )
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "env-detected-project-123")

    repo = FirestoreRepository[Elder]("elders", settings, model_cls=Elder)

    mock_client_cls = MagicMock()
    monkeypatch.setattr("google.cloud.firestore.AsyncClient", mock_client_cls)

    client = repo._get_client()
    assert client is not None
    mock_client_cls.assert_called_once_with(project="env-detected-project-123")


@pytest.mark.asyncio
async def test_seed_demo_script(test_settings: Settings) -> None:
    """Verify seed_demo creates an elder, circle, members, and sample medications."""
    result = await seed_demo(settings=test_settings)
    assert "circle_code" in result
    assert result["circle_code"].startswith("CARE-")
    assert len(result["elder_passcode"]) == 12
    assert len(result["manager_passcode"]) == 12
    assert len(result["helper_passcode"]) == 12
