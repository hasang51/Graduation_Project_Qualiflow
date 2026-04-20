"""Merge discovery + profile into the canonical dataset manifest.

Adds bucketing fields (``page_bucket``, ``size_bucket``, ``supplier_hint``)
that later stages use for balanced gold-candidate selection.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

from scripts._dataset_common import (
    DEFAULT_MANIFEST_DIR,
    ensure_dir,
    page_bucket,
    size_bucket,
)


def _load_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


_SUPPLIER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("acroni", re.compile(r"acroni", re.I)),
    ("outokumpu", re.compile(r"outokumpu", re.I)),
    ("cares", re.compile(r"cares", re.I)),
    ("megafil", re.compile(r"megafil", re.I)),
    ("tuv_rheinland", re.compile(r"t[uü]v|rheinland", re.I)),
    ("aisi", re.compile(r"aisi[-_ ]?\d+", re.I)),
    ("s235_s275_s355", re.compile(r"s(235|275|355)", re.I)),
    ("astm", re.compile(r"astm", re.I)),
    ("en10204", re.compile(r"en[ _-]?10204|3[._ ]?1b?", re.I)),
    ("pipe_mill", re.compile(r"pipe|mill", re.I)),
    ("screenshot", re.compile(r"screenshot", re.I)),
    ("stainless", re.compile(r"stainless|316|304", re.I)),
)


def guess_supplier_hint(filename: str) -> str:
    for name, pattern in _SUPPLIER_PATTERNS:
        if pattern.search(filename):
            return name
    return "unknown"


def build(discovery_path: Path, profile_path: Path, output_dir: Path) -> tuple[Path, Path]:
    discovery = {row["document_id"]: row for row in _load_jsonl(discovery_path)}
    profiles = _load_jsonl(profile_path)

    ensure_dir(output_dir)
    manifest_jsonl = output_dir / "manifest.jsonl"
    manifest_csv = output_dir / "manifest.csv"

    fieldnames = [
        "document_id",
        "filename",
        "abs_path",
        "size_bytes",
        "sha256",
        "page_count",
        "has_text_layer",
        "text_density",
        "blur_score",
        "noise_score",
        "table_presence_hint",
        "quality_class",
        "page_bucket",
        "size_bucket",
        "supplier_hint",
        "reasons",
    ]

    with manifest_jsonl.open("w", encoding="utf-8") as jsonl_out, manifest_csv.open(
        "w", encoding="utf-8", newline=""
    ) as csv_out:
        writer = csv.DictWriter(csv_out, fieldnames=fieldnames)
        writer.writeheader()
        for profile in profiles:
            doc_id = profile["document_id"]
            base = discovery.get(doc_id) or {}
            abs_path = profile.get("abs_path") or base.get("abs_path")
            size_bytes = profile.get("size_bytes") or base.get("size_bytes") or 0
            sha256 = profile.get("sha256") or base.get("sha256")
            filename = profile.get("filename") or base.get("filename", "<unknown>")
            row = {
                "document_id": doc_id,
                "filename": filename,
                "abs_path": abs_path,
                "size_bytes": size_bytes,
                "sha256": sha256,
                "page_count": profile.get("page_count", 0),
                "has_text_layer": profile.get("has_text_layer", False),
                "text_density": profile.get("text_density", 0.0),
                "blur_score": profile.get("blur_score", 0.0),
                "noise_score": profile.get("noise_score", 0.0),
                "table_presence_hint": profile.get("table_presence_hint", False),
                "quality_class": profile.get("quality_class", "scan_degraded"),
                "page_bucket": page_bucket(int(profile.get("page_count", 0) or 0)),
                "size_bucket": size_bucket(int(size_bytes or 0)),
                "supplier_hint": guess_supplier_hint(filename),
                "reasons": list(profile.get("reasons", [])),
            }
            jsonl_out.write(json.dumps(row, ensure_ascii=False) + "\n")
            csv_row = dict(row)
            csv_row["reasons"] = "|".join(row["reasons"])
            writer.writerow(csv_row)

    return manifest_jsonl, manifest_csv


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the canonical dataset manifest.")
    parser.add_argument(
        "--discovery",
        default=str(DEFAULT_MANIFEST_DIR / "documents_discovery.jsonl"),
    )
    parser.add_argument(
        "--profile",
        default=str(DEFAULT_MANIFEST_DIR / "documents_manifest.jsonl"),
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_MANIFEST_DIR),
    )
    args = parser.parse_args(argv)

    discovery_path = Path(args.discovery)
    profile_path = Path(args.profile)
    if not discovery_path.exists():
        print(f"[error] discovery manifest not found: {discovery_path}", file=sys.stderr)
        return 2
    if not profile_path.exists():
        print(f"[error] profile manifest not found: {profile_path}", file=sys.stderr)
        return 2

    manifest_jsonl, manifest_csv = build(discovery_path, profile_path, Path(args.output_dir))
    print(f"[ok] wrote {manifest_jsonl}")
    print(f"[ok] wrote {manifest_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
