from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from app.config import settings


def ensure_storage_dirs() -> None:
    for folder in ("pdfs", "artifacts", "outputs"):
        (settings.storage_dir / folder).mkdir(parents=True, exist_ok=True)
    Path("./data").mkdir(parents=True, exist_ok=True)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def persist_pdf(content: bytes, filename: str, file_hash: str) -> Path:
    ext = ".pdf"
    safe_name = "".join(ch for ch in filename if ch.isalnum() or ch in ("-", "_", ".")) or "document.pdf"
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    target = settings.storage_dir / "pdfs" / f"{timestamp}_{file_hash[:12]}_{safe_name}"
    if target.suffix.lower() != ext:
        target = target.with_suffix(ext)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


def artifact_dir_for_hash(file_hash: str) -> Path:
    folder = settings.storage_dir / "artifacts" / file_hash[:16]
    folder.mkdir(parents=True, exist_ok=True)
    return folder
