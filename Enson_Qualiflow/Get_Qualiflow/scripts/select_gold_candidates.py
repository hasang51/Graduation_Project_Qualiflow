"""Select a balanced set of gold-candidate documents.

Balancing strategy (deterministic):
1. Group by ``quality_class``.
2. Within each ``quality_class`` group, sub-group by ``page_bucket``.
3. Round-robin pick until the target N is reached or candidates are exhausted.

Output: ``data/gold_candidates/gold_candidates_manifest.csv`` /
``gold_candidates_manifest.jsonl``.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

from scripts._dataset_common import (
    DEFAULT_GOLD_CANDIDATES_DIR,
    DEFAULT_MANIFEST_DIR,
    ensure_dir,
)


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def select_balanced(manifest_rows: list[dict], n: int) -> list[dict]:
    groups: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in manifest_rows:
        quality = row.get("quality_class", "unknown")
        page_b = row.get("page_bucket", "unknown")
        groups[quality][page_b].append(row)

    # Deterministic ordering inside each (quality, page_bucket) bucket
    for quality in groups:
        for page_b in groups[quality]:
            groups[quality][page_b].sort(key=lambda r: r.get("document_id", ""))

    quality_order = ["scan_degraded", "scan_clean", "digital_clean"]
    # Ensure unknown classes still participate.
    for quality in sorted(groups.keys()):
        if quality not in quality_order:
            quality_order.append(quality)

    # Page bucket order (roughly short -> long for diversity)
    page_order = ["single", "short", "long"]

    picks: list[dict] = []
    seen_ids: set[str] = set()
    iterators = {
        (q, p): iter(groups[q].get(p, []))
        for q in quality_order
        for p in page_order
    }

    while len(picks) < n:
        progress = False
        for quality in quality_order:
            if len(picks) >= n:
                break
            for page_b in page_order:
                if len(picks) >= n:
                    break
                it = iterators.get((quality, page_b))
                if it is None:
                    continue
                for row in it:
                    if row["document_id"] in seen_ids:
                        continue
                    picks.append(row)
                    seen_ids.add(row["document_id"])
                    progress = True
                    break
        if not progress:
            break

    return picks


def write_outputs(selected: list[dict], output_dir: Path) -> tuple[Path, Path]:
    ensure_dir(output_dir)
    jsonl_path = output_dir / "gold_candidates_manifest.jsonl"
    csv_path = output_dir / "gold_candidates_manifest.csv"

    fieldnames = [
        "document_id",
        "filename",
        "abs_path",
        "quality_class",
        "page_count",
        "page_bucket",
        "size_bucket",
        "supplier_hint",
        "has_text_layer",
        "blur_score",
        "noise_score",
    ]
    with jsonl_path.open("w", encoding="utf-8") as jsonl_out, csv_path.open(
        "w", encoding="utf-8", newline=""
    ) as csv_out:
        writer = csv.DictWriter(csv_out, fieldnames=fieldnames)
        writer.writeheader()
        for row in selected:
            jsonl_out.write(json.dumps(row, ensure_ascii=False) + "\n")
            writer.writerow({key: row.get(key) for key in fieldnames})
    return jsonl_path, csv_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select a balanced gold-candidate set.")
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST_DIR / "manifest.jsonl"),
        help="Canonical manifest (from build_manifest.py).",
    )
    parser.add_argument("--n", type=int, default=20, help="Target candidate count (default 20).")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_GOLD_CANDIDATES_DIR),
    )
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"[error] manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    rows = _load_jsonl(manifest_path)
    if not rows:
        print("[error] manifest is empty", file=sys.stderr)
        return 2

    selected = select_balanced(rows, n=args.n)
    jsonl_path, csv_path = write_outputs(selected, Path(args.output_dir))
    print(f"[ok] picked {len(selected)} documents")
    breakdown: dict[str, int] = {}
    for row in selected:
        key = f"{row.get('quality_class')}::{row.get('page_bucket')}"
        breakdown[key] = breakdown.get(key, 0) + 1
    for key, count in sorted(breakdown.items()):
        print(f"    {key}: {count}")
    print(f"[ok] wrote {jsonl_path}")
    print(f"[ok] wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
