from __future__ import annotations

from app.services.storage.base import ObjectStorageBackend
from config.settings import get_settings


class S3StorageBackend(ObjectStorageBackend):
    def __init__(self) -> None:
        settings = get_settings()
        import boto3
        from botocore.config import Config

        session_kwargs: dict = {
            "aws_access_key_id": settings.s3_access_key_id or None,
            "aws_secret_access_key": settings.s3_secret_access_key or None,
            "region_name": settings.s3_region,
        }
        client_kwargs: dict = {"config": Config(signature_version="s3v4")}
        if settings.s3_endpoint_url:
            client_kwargs["endpoint_url"] = settings.s3_endpoint_url

        self._bucket = settings.s3_bucket_name
        self._client = boto3.client("s3", **session_kwargs, **client_kwargs)

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)
        return key

    def get_bytes(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)
