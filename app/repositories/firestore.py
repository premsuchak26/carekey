"""Google Cloud Firestore repository adapter.

Provides production persistent storage backed by Firestore collections.
"""

from typing import Any, TypeVar

from app.config import Settings

T = TypeVar("T")


class FirestoreRepository[T]:
    """Firestore-backed repository implementation."""

    def __init__(self, collection_name: str, settings: Settings) -> None:
        """Initialize the Firestore repository.

        Args:
            collection_name: Firestore target collection name.
            settings: Application settings containing project ID and credentials info.
        """
        self.collection_name = collection_name
        self.settings = settings
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-initialize Firestore client.

        Returns:
            google.cloud.firestore.AsyncClient instance.
        """
        if self._client is None:
            # Deferred import so module can load in environments without GCP credentials
            from google.cloud import firestore

            project = self.settings.firestore_project_id
            self._client = firestore.AsyncClient(project=project)
        return self._client

    async def get(self, entity_id: str) -> T | None:
        """Fetch document by ID from Firestore collection.

        Args:
            entity_id: The document key identifier.

        Returns:
            The document dictionary or None if not found.
        """
        client = self._get_client()
        doc_ref = client.collection(self.collection_name).document(entity_id)
        snapshot = await doc_ref.get()
        if not snapshot.exists:
            return None
        data: T = snapshot.to_dict()
        return data

    async def list_all(self, limit: int = 100) -> list[T]:
        """Fetch documents from collection up to limit.

        Args:
            limit: Maximum count of documents.

        Returns:
            List of document dictionaries.
        """
        client = self._get_client()
        docs_stream = client.collection(self.collection_name).limit(limit).stream()
        results: list[T] = []
        async for doc in docs_stream:
            results.append(doc.to_dict())
        return results

    async def save(self, entity_id: str, data: T) -> None:
        """Store or overwrite document by ID.

        Args:
            entity_id: Unique document identifier.
            data: Data payload to store.
        """
        client = self._get_client()
        doc_ref = client.collection(self.collection_name).document(entity_id)
        payload = data if isinstance(data, dict) else dict(data)  # type: ignore[call-overload]
        await doc_ref.set(payload)

    async def delete(self, entity_id: str) -> bool:
        """Delete document by ID.

        Args:
            entity_id: Document identifier to remove.

        Returns:
            True once delete operation completes.
        """
        client = self._get_client()
        doc_ref = client.collection(self.collection_name).document(entity_id)
        await doc_ref.delete()
        return True

    async def ping(self) -> bool:
        """Check Firestore connectivity.

        Returns:
            True if connection check succeeds, False otherwise.
        """
        try:
            client = self._get_client()
            # Minimal collection query to verify read connectivity
            _ = client.collection(self.collection_name).limit(1)
            return True
        except Exception:
            return False
