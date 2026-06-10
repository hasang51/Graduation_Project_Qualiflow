"""Shared helpers for the dataset workflow scripts."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_DATASET_ROOT = Path(
    r"C:\Users\DELL\Downloads\Mill Test CertificateS\Mill Test CertificateS"
)

DEFAULT_MANIFEST_DIR = Path("data/manifests")
DEFAULT_GOLD_CANDIDATES_DIR = Path("data/gold_candidates")
DEFAULT_GOLD_VERIFIED_DIR = Path("data/gold_verified")
DEFAULT_BATCH_RUNS_DIR = Path("data/batch_runs")
DEFAULT_EVAL_DIR = Path("outputs/eval_runs")


@dataclass(frozen=True)
class DiscoveredDocument:
    document_id: str
    filename: str
    abs_path: str
    size_bytes: int
    sha256: str


def resolve_dataset_root(cli_root: str | None) -> Path:
    """Priority: CLI arg > QUALIFLOW_DATASET_ROOT env > DEFAULT_DATASET_ROOT."""

    if cli_root:
        return Path(cli_root).expanduser().resolve()
    env = os.environ.get("QUALIFLOW_DATASET_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_DATASET_ROOT


def sha256_of_file(path: Path, chunk: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            hasher.update(block)
    return hasher.hexdigest()


def iter_pdfs(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for candidate in sorted(root.rglob("*.pdf")):
        if candidate.is_file():
            yield candidate


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def page_bucket(page_count: int) -> str:
    if page_count <= 1:
        return "single"
    if page_count <= 4:
        return "short"
    return "long"


def size_bucket(size_bytes: int) -> str:
    if size_bytes < 200 * 1024:
        return "xs"
    if size_bytes < 1 * 1024 * 1024:
        return "s"
    if size_bytes < 4 * 1024 * 1024:
        return "m"
    if size_bytes < 12 * 1024 * 1024:
        return "l"
    return "xl"
