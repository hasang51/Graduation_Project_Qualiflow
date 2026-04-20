"""Discover all PDFs under a dataset root and emit a discovery manifest.

Usage::

    python -m scripts.discover_documents
    python -m scripts.discover_documents --dataset-root "D:\\path\\to\\pdfs"

Outputs (defaults under ``data/manifests/``):
    documents_discovery.jsonl    — one JSON object per PDF
    documents_discovery.csv      — flat CSV of the same data
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

from scripts._dataset_common import (
    DEFAULT_MANIFEST_DIR,
    DiscoveredDocument,
    ensure_dir,
    iter_pdfs,
    resolve_dataset_root,
    sha256_of_file,
)


def discover(root: Path) -> list[DiscoveredDocument]:
    documents: list[DiscoveredDocument] = []
    for pdf_path in iter_pdfs(root):
        try:
            size_bytes = pdf_path.stat().st_size
        except OSError:
            continue
        try:
            sha256 = sha256_of_file(pdf_path)
        except OSError as exc:
            print(f"[warn] cannot read {pdf_path.name}: {exc}", file=sys.stderr)
            continue
        documents.append(
            DiscoveredDocument(
                document_id=sha256[:16],
                filename=pdf_path.name,
                abs_path=str(pdf_path.resolve()),
                size_bytes=size_bytes,
                sha256=sha256,
            )
        )
    return documents


def write_outputs(documents: list[DiscoveredDocument], output_dir: Path) -> tuple[Path, Path]:
    ensure_dir(output_dir)
    jsonl_path = output_dir / "documents_discovery.jsonl"
    csv_path = output_dir / "documents_discovery.csv"

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for doc in documents:
            handle.write(json.dumps(asdict(doc), ensure_ascii=False) + "\n")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["document_id", "filename", "abs_path", "size_bytes", "sha256"],
        )
        writer.writeheader()
        for doc in documents:
            writer.writerow(asdict(doc))

    return jsonl_path, csv_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover PDFs for the QualiFlow dataset workflow.")
    parser.add_argument("--dataset-root", default=None, help="Root folder to scan for PDFs.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_MANIFEST_DIR),
        help=f"Where to write manifests (default: {DEFAULT_MANIFEST_DIR}).",
    )
    args = parser.parse_args(argv)

    root = resolve_dataset_root(args.dataset_root)
    if not root.exists():
        print(f"[error] dataset root does not exist: {root}", file=sys.stderr)
        return 2

    print(f"[info] scanning {root}")
    documents = discover(root)
    print(f"[info] discovered {len(documents)} PDFs")

    jsonl_path, csv_path = write_outputs(documents, Path(args.output_dir))
    print(f"[ok] wrote {jsonl_path}")
    print(f"[ok] wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
