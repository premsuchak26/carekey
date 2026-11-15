"""Tests for the /healthz health check endpoint."""

from fastapi import status
from fastapi.testclient import TestClient

from app.config import Settings


def test_healthz_endpoint_returns_200(client: TestClient, test_settings: Settings) -> None:
    """Verify that GET /healthz returns 200 OK and valid health metadata.

    Args:
        client: TestClient fixture.
        test_settings: Active test settings.
    """
    response = client.get("/healthz")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == test_settings.app_name
    assert data["environment"] == "test"
    assert data["repository_backend"] == "memory"
    assert data["repository_type"] == "memory"
