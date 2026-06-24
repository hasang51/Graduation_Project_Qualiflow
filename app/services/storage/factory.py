from __future__ import annotations

from functools import lru_cache

from app.services.storage.base import ObjectStorageBackend
from app.services.storage.local import LocalStorageBackend
from config.settings import get_settings


@lru_cache
def get_storage_backend() -> ObjectStorageBackend:
    settings = get_settings()
    if settings.object_storage_backend == "s3":
        from app.services.storage.s3 import S3StorageBackend

        return S3StorageBackend()
    return LocalStorageBackend()


def reset_storage_backend_cache() -> None:
    get_storage_backend.cache_clear()
