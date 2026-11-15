"""Google Cloud Firestore repository adapter.

Provides production persistent storage backed by Firestore collections.
"""

import os
from collections.abc import Callable
from typing import Any, TypeVar

from app.config import Settings

T = TypeVar("T")


class FirestoreRepository[T]:
    """Firestore-backed repository implementation."""

    def __init__(
        self,
        collection_name: str,
        settings: Settings,
        model_cls: type[T] | None = None,
    ) -> None:
        """Initialize the Firestore repository.

        Args:
            collection_name: Firestore target collection name.
            settings: Application settings containing project ID and credentials info.
            model_cls: Optional Pydantic model class for typed entity deserialization.
        """
        self.collection_name = collection_name
        self.settings = settings
        self.model_cls = model_cls
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-initialize Firestore client using default Google credentials.

        Returns:
            google.cloud.firestore.AsyncClient instance.
        """
        if self._client is None:
            # Deferred import so module can load in environments without GCP libraries/credentials
            from google.cloud import firestore

            project = (
                self.settings.firestore_project_id
                or os.environ.get("GOOGLE_CLOUD_PROJECT")
                or os.environ.get("GCP_PROJECT")
                or os.environ.get("GCLOUD_PROJECT")
            )
            if project:
                self._client = firestore.AsyncClient(project=project)
            else:
                self._client = firestore.AsyncClient()
        return self._client

    def _to_entity(self, data: dict[str, Any], doc_id: str | None = None) -> T:
        """Convert Firestore raw document data to typed entity or model."""
        if doc_id and "id" not in data:
            data["id"] = doc_id
        if self.model_cls is not None and hasattr(self.model_cls, "model_validate"):
            validated = self.model_cls.model_validate(data)  # type: ignore[attr-defined]
            return validated  # type: ignore[no-any-return]
        return data  # type: ignore[return-value]

    def _to_dict(self, entity: T) -> dict[str, Any]:
        """Convert typed entity to Firestore document dictionary."""
        if hasattr(entity, "model_dump"):
            dumped = entity.model_dump(mode="json")
            return dict(dumped)
        if isinstance(entity, dict):
            return dict(entity)
        return dict(entity)  # type: ignore[call-overload,no-any-return]

    async def get(self, entity_id: str) -> T | None:
        """Fetch document by ID from Firestore collection."""
        client = self._get_client()
        doc_ref = client.collection(self.collection_name).document(entity_id)
        snapshot = await doc_ref.get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        if data is None:
            return None
        return self._to_entity(data, doc_id=snapshot.id)

    async def list_all(self, limit: int = 1000) -> list[T]:
        """Fetch documents from collection up to limit."""
        client = self._get_client()
        ref = client.collection(self.collection_name)
        docs_stream = ref.limit(limit).stream() if limit and limit > 0 else ref.stream()

        results: list[T] = []
        async for doc in docs_stream:
            data = doc.to_dict()
            if data is not None:
                results.append(self._to_entity(data, doc_id=doc.id))
        return results

    async def find(self, predicate: Callable[[T], bool]) -> list[T]:
        """Filter items matching predicate in application code.

        Avoids multi-field composite indexes on Firestore collections.
        """
        all_items = await self.list_all(limit=5000)
        return [item for item in all_items if predicate(item)]

    async def save(self, entity_id: str, data: T) -> None:
        """Store or overwrite document by ID."""
        client = self._get_client()
        doc_ref = client.collection(self.collection_name).document(entity_id)
        payload = self._to_dict(data)
        await doc_ref.set(payload)

    async def delete(self, entity_id: str) -> bool:
        """Delete document by ID."""
        client = self._get_client()
        doc_ref = client.collection(self.collection_name).document(entity_id)
        await doc_ref.delete()
        return True

    async def ping(self) -> bool:
        """Check Firestore connectivity."""
        try:
            client = self._get_client()
            query = client.collection(self.collection_name).limit(1)
            async for _ in query.stream():
                break
            return True
        except Exception:
            return False
