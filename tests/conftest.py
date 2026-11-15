"""Shared pytest fixtures for the CareKey test suite."""

import os
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Force in-memory repository backend so tests never touch the network or Google libraries
os.environ["REPOSITORY_BACKEND"] = "memory"
os.environ["REPOSITORY_TYPE"] = "memory"
os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
os.environ.pop("FIRESTORE_PROJECT_ID", None)

from app.config import Settings, get_settings
from app.main import create_app
from app.repositories import RepositoryContainer, get_repository_container


@pytest.fixture(autouse=True)
def force_in_memory_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure in-memory repository backend is forced and settings cache cleared."""
    monkeypatch.setenv("REPOSITORY_BACKEND", "memory")
    monkeypatch.setenv("REPOSITORY_TYPE", "memory")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("FIRESTORE_PROJECT_ID", raising=False)
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def guard_google_libraries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disallow any Google Cloud Firestore client or auth calls during test runs."""

    def _blocked(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(
            "Tests are configured to use in-memory backend; "
            "attempted to access Google Cloud / Firestore!"
        )

    monkeypatch.setattr("google.cloud.firestore.AsyncClient", _blocked, raising=False)
    monkeypatch.setattr("google.cloud.firestore.Client", _blocked, raising=False)
    monkeypatch.setattr("google.auth.default", _blocked, raising=False)


@pytest.fixture
def test_settings() -> Settings:
    """Provide isolated application settings for testing."""
    return Settings(
        app_name="CareKey-Test",
        environment="test",
        debug=True,
        repository_backend="memory",
        secret_key="test-secret-key-not-for-production",
    )


@pytest.fixture(autouse=True)
def clear_repositories(test_settings: Settings) -> None:
    """Reset repository container storage before each test."""
    container = get_repository_container(settings=test_settings)
    container.clear()


@pytest.fixture
def test_repos(test_settings: Settings) -> RepositoryContainer:
    """Provide repository container for direct unit testing."""
    return get_repository_container(settings=test_settings)


@pytest.fixture
def client(test_settings: Settings) -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient configured with test settings.

    Args:
        test_settings: Isolated test configuration.

    Yields:
        TestClient configured for immediate synchronous HTTP requests.
    """
    app = create_app(settings=test_settings)
    app.dependency_overrides[get_settings] = lambda: test_settings
    with TestClient(app=app) as test_client:
        yield test_client
