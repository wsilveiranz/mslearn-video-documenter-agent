"""Azure Blob Storage service client for video file staging and keyframe storage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob import BlobSasPermissions, generate_blob_sas
from azure.storage.blob.aio import BlobServiceClient

from src.config import Settings, get_settings
from src.utils.url import url_join

logger = structlog.get_logger()


class BlobStorageService:
    """Azure Blob Storage client for video file staging and keyframe storage."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._credential = DefaultAzureCredential()
        self._client = BlobServiceClient(
            account_url=self._settings.blob_account_url,
            credential=self._credential,
        )

    @property
    def _container(self) -> str:
        return self._settings.blob_container_name

    @property
    def _account_name(self) -> str:
        # Extract account name from URL: https://<account>.blob.core.windows.net
        url = self._settings.blob_account_url
        return url.split("//")[-1].split(".")[0]

    async def upload_video(self, local_path: str | Path, video_id: str) -> str:
        """Upload a video file to blob storage.

        Uploads to: {container}/{video_id}/{filename}

        Returns:
            Full blob URL.
        """
        local_path = Path(local_path)
        blob_name = f"{video_id}/{local_path.name}"
        logger.info("blob.upload_started", video_id=video_id, blob_name=blob_name)
        try:
            blob_client = self._client.get_blob_client(
                container=self._container, blob=blob_name
            )
            with local_path.open("rb") as f:
                await blob_client.upload_blob(f, overwrite=True)
            url: str = blob_client.url
            logger.info(
                "blob.upload_completed",
                video_id=video_id,
                blob_name=blob_name,
                url=url,
            )
            return url
        except Exception as e:
            logger.error("blob.upload_failed", video_id=video_id, blob_name=blob_name, error=str(e))
            raise

    async def generate_sas_url(self, blob_name: str, expiry_hours: int = 2) -> str:
        """Generate a time-limited SAS URL for a blob.

        Uses UserDelegationKey-based SAS (no account key needed).

        Returns:
            Full blob URL with SAS token appended.
        """
        logger.info("blob.sas_url_requested", blob_name=blob_name, expiry_hours=expiry_hours)
        try:
            now = datetime.now(tz=UTC)
            expiry = now + timedelta(hours=expiry_hours)
            user_delegation_key = await self._client.get_user_delegation_key(
                key_start_time=now,
                key_expiry_time=expiry,
            )
            sas_token = generate_blob_sas(
                account_name=self._account_name,
                container_name=self._container,
                blob_name=blob_name,
                user_delegation_key=user_delegation_key,
                permission=BlobSasPermissions(read=True),
                expiry=expiry,
            )
            url = f"{url_join(self._settings.blob_account_url, self._container, blob_name)}?{sas_token}"
            logger.info("blob.sas_url_generated", blob_name=blob_name, expiry_hours=expiry_hours)
            return url
        except Exception as e:
            logger.error("blob.sas_url_failed", blob_name=blob_name, error=str(e))
            raise

    async def upload_keyframe(
        self, image_data: bytes, video_id: str, keyframe_id: str
    ) -> str:
        """Upload a keyframe image to blob storage.

        Uploads to: {container}/{video_id}/keyframes/{keyframe_id}.png

        Returns:
            Full blob URL.
        """
        blob_name = f"{video_id}/keyframes/{keyframe_id}.png"
        logger.info("blob.keyframe_upload_started", video_id=video_id, blob_name=blob_name)
        try:
            blob_client = self._client.get_blob_client(
                container=self._container, blob=blob_name
            )
            await blob_client.upload_blob(image_data, overwrite=True)
            url: str = blob_client.url
            logger.info(
                "blob.keyframe_upload_completed",
                video_id=video_id,
                blob_name=blob_name,
                url=url,
            )
            return url
        except Exception as e:
            logger.error(
                "blob.keyframe_upload_failed",
                video_id=video_id,
                blob_name=blob_name,
                error=str(e),
            )
            raise

    async def download_blob(self, blob_name: str, local_path: str | Path) -> Path:
        """Download a blob to a local file path.

        Returns:
            Path to the downloaded file.
        """
        local_path = Path(local_path)
        logger.info("blob.download_started", blob_name=blob_name, local_path=str(local_path.name))
        try:
            blob_client = self._client.get_blob_client(
                container=self._container, blob=blob_name
            )
            local_path.parent.mkdir(parents=True, exist_ok=True)
            with local_path.open("wb") as f:
                stream = await blob_client.download_blob()
                await stream.readinto(f)
            logger.info("blob.download_completed", blob_name=blob_name)
            return local_path
        except Exception as e:
            logger.error("blob.download_failed", blob_name=blob_name, error=str(e))
            raise

    async def delete_video_blobs(self, video_id: str) -> int:
        """Delete all blobs for a given video_id (cleanup).

        Returns:
            Number of blobs deleted.
        """
        prefix = f"{video_id}/"
        logger.info("blob.delete_started", video_id=video_id, prefix=prefix)
        deleted = 0
        try:
            container_client = self._client.get_container_client(self._container)
            async for blob in container_client.list_blobs(name_starts_with=prefix):
                await container_client.delete_blob(blob.name)
                deleted += 1
            logger.info("blob.delete_completed", video_id=video_id, deleted=deleted)
            return deleted
        except Exception as e:
            logger.error("blob.delete_failed", video_id=video_id, error=str(e))
            raise

    async def close(self) -> None:
        """Close the async blob client and credential."""
        await self._client.close()
        await self._credential.close()

    async def __aenter__(self) -> BlobStorageService:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
