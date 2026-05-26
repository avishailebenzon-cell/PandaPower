import logging
from datetime import datetime, timedelta

from typing import Any

logger = logging.getLogger(__name__)


class SupabaseStorageManager:
    def __init__(self, supabase_client: Any):
        self.supabase = supabase_client
        self.bucket_name = "cvs"

    async def ensure_bucket_exists(self) -> None:
        try:
            buckets = await self.supabase.storage.list_buckets()
            bucket_exists = any(b.name == self.bucket_name for b in buckets)

            if not bucket_exists:
                await self.supabase.storage.create_bucket(
                    self.bucket_name,
                    options={"public": False},
                )
                logger.info(f"Created storage bucket: {self.bucket_name}")
        except Exception as e:
            logger.warning(f"Error checking/creating bucket: {e}")

    async def upload_file(
        self,
        path: str,
        content: bytes,
        content_type: str,
    ) -> str:
        try:
            # AsyncClient.storage.from_(...).upload(...) is awaitable
            await self.supabase.storage.from_(self.bucket_name).upload(
                path,
                content,
                {
                    "content-type": content_type,
                },
            )
            logger.info(f"Uploaded file to {path}")
            return path
        except Exception as e:
            logger.error(f"Failed to upload file: {e}")
            raise

    async def download_file(self, path: str) -> bytes:
        """Download a file from Supabase Storage. Uses the async client."""
        try:
            response = await self.supabase.storage.from_(self.bucket_name).download(path)
            return response
        except Exception as e:
            logger.error(f"Failed to download file: {e}")
            raise

    async def create_signed_url(self, path: str, expires_in_seconds: int = 604800) -> str:
        try:
            response = await self.supabase.storage.from_(self.bucket_name).create_signed_url(
                path,
                expires_in=expires_in_seconds,
            )
            return response["signedURL"]
        except Exception as e:
            logger.error(f"Failed to create signed URL: {e}")
            raise
