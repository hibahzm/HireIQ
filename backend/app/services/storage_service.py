from __future__ import annotations

from pathlib import Path

from app.config import get_settings


class StorageService:
    def __init__(self) -> None:
        self._settings = get_settings()

    async def upload(self, key: str, data: bytes) -> None:
        if self._settings.STORAGE_BACKEND == "azure":
            await self._azure_upload(key, data)
        else:
            self._local_upload(key, data)

    async def download(self, key: str) -> bytes:
        if self._settings.STORAGE_BACKEND == "azure":
            return await self._azure_download(key)
        return self._local_download(key)

    async def delete(self, key: str) -> None:
        if self._settings.STORAGE_BACKEND == "azure":
            await self._azure_delete(key)
        else:
            self._local_delete(key)

    # ── local filesystem ──────────────────────────────────────────────────────

    def _local_path(self, key: str) -> Path:
        base = Path(self._settings.STORAGE_LOCAL_PATH)
        base.mkdir(parents=True, exist_ok=True)
        return base / key

    def _local_upload(self, key: str, data: bytes) -> None:
        path = self._local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def _local_download(self, key: str) -> bytes:
        return self._local_path(key).read_bytes()

    def _local_delete(self, key: str) -> None:
        path = self._local_path(key)
        if path.exists():
            path.unlink()

    # ── Azure Blob Storage ────────────────────────────────────────────────────

    async def _azure_upload(self, key: str, data: bytes) -> None:
        from azure.storage.blob.aio import BlobServiceClient

        async with BlobServiceClient.from_connection_string(
            self._settings.AZURE_STORAGE_CONNECTION_STRING
        ) as client:
            blob = client.get_blob_client(
                container=self._settings.AZURE_STORAGE_CONTAINER, blob=key
            )
            await blob.upload_blob(data, overwrite=True)

    async def _azure_download(self, key: str) -> bytes:
        from azure.storage.blob.aio import BlobServiceClient

        async with BlobServiceClient.from_connection_string(
            self._settings.AZURE_STORAGE_CONNECTION_STRING
        ) as client:
            blob = client.get_blob_client(
                container=self._settings.AZURE_STORAGE_CONTAINER, blob=key
            )
            stream = await blob.download_blob()
            return await stream.readall()

    async def _azure_delete(self, key: str) -> None:
        from azure.storage.blob.aio import BlobServiceClient

        async with BlobServiceClient.from_connection_string(
            self._settings.AZURE_STORAGE_CONNECTION_STRING
        ) as client:
            blob = client.get_blob_client(
                container=self._settings.AZURE_STORAGE_CONTAINER, blob=key
            )
            await blob.delete_blob(delete_snapshots="include")
