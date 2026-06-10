"""Build canonical manifest and metadata for the 20-document evaluation set.

Reads PDFs from ``data/eval_docs/``, optionally merges ``quality_bucket`` from
``data/metadata.csv``, and writes:

- ``data/manifest_20.jsonl``
- ``data/gold/metadata_20.csv``
- ``data/gold/metadata.csv`` (backward-compatible copy of ``metadata_20.csv``)
- ``data/final20_dataset_summary.json``

Usage::

    python -m scripts.prepare_final20_metadata
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

VALID_QUALITY_BUCKETS = frozenset({"digital_pdf", "clean_scan", "degraded_scan", "severe_scan"})
DOC_IDS = [f"doc{i:03d}" for i in range(1, 21)]
DOCUMENT_TYPE = "Mill Test Certificate"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_quality_buckets_from_csv(path: Path) -> dict[str, str]:
    """Map doc_id -> quality_bucket when the bucket is one of VALID_QUALITY_BUCKETS."""

    out: dict[str, str] = {}
    if not path.is_file():
        return out

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            doc_id = (row.get("doc_id") or "").strip()
            if not doc_id:
                continue
            raw = (row.get("quality_bucket") or "").strip()
            if raw in VALID_QUALITY_BUCKETS:
                out[doc_id] = raw
    return out


def _infer_quality_bucket(*, has_text_layer: bool, text_chars: int) -> str:
    if has_text_layer and text_chars > 500:
        return "digital_pdf"
    if has_text_layer:
        return "clean_scan"
    return "degraded_scan"


def _pdf_profile(pdf_path: Path) -> tuple[int, int, bool]:
    """Return (page_count, text_chars, has_text_layer)."""

    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages = len(reader.pages)
    chunks: list[str] = []
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            chunks.append(extracted)
    raw_text = "".join(chunks)
    text_chars = len(raw_text)
    has_text_layer = len(raw_text.strip()) > 30
    return pages, text_chars, has_text_layer


def _validate_eval_docs(eval_dir: Path) -> None:
    expected = {f"{did}.pdf" for did in DOC_IDS}
    present = {p.name for p in eval_dir.glob("*.pdf") if p.is_file()}
    missing = sorted(expected - present)
    extras = sorted(present - expected)

    if missing or extras or len(present) != 20:
        print("[error] data/eval_docs must contain exactly doc001.pdf … doc020.pdf.", file=sys.stderr)
        if missing:
            print(f"  Missing ({len(missing)}): {', '.join(missing)}", file=sys.stderr)
        if extras:
            print(f"  Unexpected PDFs ({len(extras)}): {', '.join(extras)}", file=sys.stderr)
        if len(present) != 20:
            print(f"  Expected 20 PDFs, found {len(present)}.", file=sys.stderr)
        sys.exit(1)


def _validate_gold_json(gold_dir: Path) -> None:
    expected = {f"{did}.json" for did in DOC_IDS}
    present = {p.name for p in gold_dir.glob("*.json") if p.is_file()}
    missing = sorted(expected - present)
    extras = sorted(present - expected)

    if missing or extras or len(present) != 20:
        print("[error] data/gold/ground_truth must contain exactly doc001.json … doc020.json.", file=sys.stderr)
        if missing:
            print(f"  Missing ({len(missing)}): {', '.join(missing)}", file=sys.stderr)
        if extras:
            print(f"  Unexpected JSON files ({len(extras)}): {', '.join(extras)}", file=sys.stderr)
        print(f"  Expected 20 JSON files, found {len(present)}.", file=sys.stderr)
        sys.exit(1)


def run(*, root: Path | None = None) -> dict:
    root = root or _project_root()
    eval_dir = root / "data" / "eval_docs"
    gold_dir = root / "data" / "gold" / "ground_truth"
    legacy_meta = root / "data" / "metadata.csv"

    if not eval_dir.is_dir():
        print(f"[error] eval docs directory not found: {eval_dir}", file=sys.stderr)
        sys.exit(1)
    if not gold_dir.is_dir():
        print(f"[error] gold directory not found: {gold_dir}", file=sys.stderr)
        sys.exit(1)

    _validate_eval_docs(eval_dir)
    _validate_gold_json(gold_dir)

    preserved_buckets = _load_quality_buckets_from_csv(legacy_meta)

    manifest_path = root / "data" / "manifest_20.jsonl"
    meta_out_path = root / "data" / "gold" / "metadata_20.csv"
    summary_path = root / "data" / "final20_dataset_summary.json"

    meta_out_path.parent.mkdir(parents=True, exist_ok=True)

    csv_fieldnames = [
        "doc_id",
        "file_name",
        "quality_bucket",
        "document_type",
        "pages",
        "has_text_layer",
        "text_chars",
        "size_kb",
        "ground_truth_path",
    ]

    page_counts: list[int] = []
    total_text_chars = 0
    total_size_bytes = 0
    with_text = 0
    bucket_counter: Counter[str] = Counter()

    with manifest_path.open("w", encoding="utf-8") as jsonl_out, meta_out_path.open(
        "w", encoding="utf-8", newline=""
    ) as csv_out:
        writer = csv.DictWriter(csv_out, fieldnames=csv_fieldnames)
        writer.writeheader()

        for doc_id in DOC_IDS:
            pdf_path = (eval_dir / f"{doc_id}.pdf").resolve()
            rel_pdf = f"data/eval_docs/{doc_id}.pdf"
            gt_rel = f"data/gold/ground_truth/{doc_id}.json"

            pages, text_chars, has_tl = _pdf_profile(pdf_path)
            size_bytes = pdf_path.stat().st_size
            total_size_bytes += size_bytes
            size_kb = round(size_bytes / 1024.0, 1)

            qb = preserved_buckets.get(doc_id)
            if qb not in VALID_QUALITY_BUCKETS:
                qb = _infer_quality_bucket(has_text_layer=has_tl, text_chars=text_chars)

            page_counts.append(pages)
            total_text_chars += text_chars
            if has_tl:
                with_text += 1
            bucket_counter[qb] += 1

            has_tl_str = "TRUE" if has_tl else "FALSE"

            manifest_line = {
                "document_id": doc_id,
                "filename": f"{doc_id}.pdf",
                "path": rel_pdf,
                "abs_path": str(pdf_path),
                "ground_truth_path": gt_rel,
            }
            jsonl_out.write(json.dumps(manifest_line, ensure_ascii=False) + "\n")

            writer.writerow(
                {
                    "doc_id": doc_id,
                    "file_name": f"{doc_id}.pdf",
                    "quality_bucket": qb,
                    "document_type": DOCUMENT_TYPE,
                    "pages": str(pages),
                    "has_text_layer": has_tl_str,
                    "text_chars": str(text_chars),
                    "size_kb": str(size_kb),
                    "ground_truth_path": gt_rel,
                }
            )

    page_dist = Counter(str(p) for p in page_counts)
    summary = {
        "total_pdfs": 20,
        "total_gold_json": 20,
        "total_pages": sum(page_counts),
        "documents_with_text_layer": with_text,
        "documents_without_text_layer": 20 - with_text,
        "total_text_chars": total_text_chars,
        "total_size_kb": round(total_size_bytes / 1024.0, 1),
        "quality_bucket_counts": dict(sorted(bucket_counter.items())),
        "page_count_distribution": dict(sorted(page_dist.items(), key=lambda kv: int(kv[0]))),
    }

    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.copy2(meta_out_path, meta_out_path.parent / "metadata.csv")
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Prepare manifest + metadata for the final 20 PDF evaluation set.")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Project root (default: parent of scripts/).",
    )
    args = parser.parse_args(argv)

    summary = run(root=args.root)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
