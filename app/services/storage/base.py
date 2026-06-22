from __future__ import annotations

from abc import ABC, abstractmethod


class ObjectStorageBackend(ABC):
    @abstractmethod
    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        raise NotImplementedError

    @abstractmethod
    def get_bytes(self, key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError
