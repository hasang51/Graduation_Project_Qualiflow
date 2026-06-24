from __future__ import annotations

from pathlib import Path

from app.services.storage.base import ObjectStorageBackend
from config.settings import get_settings


class LocalStorageBackend(ObjectStorageBackend):
    def __init__(self, root: Path | None = None) -> None:
        settings = get_settings()
        self.root = (root or settings.storage_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        safe_key = key.lstrip("/").replace("..", "_")
        path = (self.root / safe_key).resolve()
        if not str(path).startswith(str(self.root)):
            raise ValueError("Invalid storage key.")
        return path

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get_bytes(self, key: str) -> bytes:
        path = self._path_for(key)
        if not path.exists():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path_for(key).exists()

    def delete(self, key: str) -> None:
        path = self._path_for(key)
        if path.exists():
            path.unlink()
