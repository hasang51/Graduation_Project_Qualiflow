"""Build a human-review pack from a batch-run over the gold candidates.

Outputs, under ``data/gold_candidates/``:
- ``gold_candidates_prefill.jsonl`` — one record per candidate with the model's
  extracted metadata + mechanical properties, clearly labelled as PREANNOTATED.
- ``annotation_sheet.csv`` — flat, reviewer-friendly CSV. The first row is a
  banner row that says the contents are NOT verified gold truth.

Reviewers copy the prefill columns into the ``verified_*`` columns to produce
final gold, then move the accepted rows into ``data/gold_verified/``.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from scripts._dataset_common import (
    DEFAULT_BATCH_RUNS_DIR,
    DEFAULT_GOLD_CANDIDATES_DIR,
    ensure_dir,
)

BANNER_COMMENT = (
    "PREANNOTATED — NOT VERIFIED — REQUIRES HUMAN REVIEW. "
    "Columns prefixed `extracted_` come from the multimodal pipeline and "
    "may be wrong. Fill the `verified_*` columns with reviewer truth."
)

FIELDS = [
    "document_id",
    "filename",
    "quality_class",
    "route_used",
    "extracted_supplier_name",
    "extracted_document_type",
    "extracted_certificate_date",
    "extracted_is_compliant",
    "extracted_confidence_score",
    "extracted_total_items_detected",
    "extracted_heat_numbers",
    "extracted_grades",
    "extracted_yield_strength_mpa",
    "extracted_tensile_strength_mpa",
    "extracted_elongation_percentage",
    "structured_review_reasons",
    # reviewer override columns — leave blank; fill during human review
    "verified_supplier_name",
    "verified_document_type",
    "verified_certificate_date",
    "verified_is_compliant",
    "verified_heat_numbers",
    "verified_grades",
    "verified_yield_strength_mpa",
    "verified_tensile_strength_mpa",
    "verified_elongation_percentage",
    "review_status",
    "reviewer_notes",
]


def _pipe_list(values: list) -> str:
    cleaned = [str(v).strip() for v in values if v not in (None, "")]
    return "|".join(cleaned)


def build_prefill_record(per_document: dict) -> dict:
    extraction = per_document.get("extraction") or {}
    items = extraction.get("items") or []

    heats: list[str] = []
    grades: list[str] = []
    yields: list[float] = []
    tensiles: list[float] = []
    elongs: list[float] = []
    for item in items:
        if item.get("heat_number"):
            heats.append(item["heat_number"])
        if item.get("grade"):
            grades.append(item["grade"])
        mp = item.get("mechanical_properties") or {}
        if mp.get("yield_strength_mpa") is not None:
            yields.append(mp["yield_strength_mpa"])
        if mp.get("tensile_strength_mpa") is not None:
            tensiles.append(mp["tensile_strength_mpa"])
        if mp.get("elongation_percentage") is not None:
            elongs.append(mp["elongation_percentage"])

    review = per_document.get("review_policy") or {}

    return {
        "document_id": per_document.get("document_id"),
        "filename": per_document.get("filename"),
        "quality_class": (per_document.get("profile") or {}).get("quality_class"),
        "route_used": per_document.get("route_used"),
        "extracted_supplier_name": extraction.get("supplier_name"),
        "extracted_document_type": extraction.get("document_type"),
        "extracted_certificate_date": extraction.get("certificate_date"),
        "extracted_is_compliant": extraction.get("is_compliant"),
        "extracted_confidence_score": extraction.get("confidence_score"),
        "extracted_total_items_detected": extraction.get("total_items_detected"),
        "extracted_heat_numbers": _pipe_list(heats),
        "extracted_grades": _pipe_list(grades),
        "extracted_yield_strength_mpa": _pipe_list(yields),
        "extracted_tensile_strength_mpa": _pipe_list(tensiles),
        "extracted_elongation_percentage": _pipe_list(elongs),
        "structured_review_reasons": _pipe_list(review.get("structured_reasons") or []),
        "verified_supplier_name": "",
        "verified_document_type": "",
        "verified_certificate_date": "",
        "verified_is_compliant": "",
        "verified_heat_numbers": "",
        "verified_grades": "",
        "verified_yield_strength_mpa": "",
        "verified_tensile_strength_mpa": "",
        "verified_elongation_percentage": "",
        "review_status": "PENDING_REVIEW",
        "reviewer_notes": "",
    }


def run(run_dir: Path, candidate_manifest: Path | None, output_dir: Path) -> tuple[Path, Path]:
    per_doc_dir = run_dir / "per_document"
    if not per_doc_dir.exists():
        raise FileNotFoundError(f"No per_document/ under {run_dir}")

    allowed_ids: set[str] | None = None
    if candidate_manifest is not None and candidate_manifest.exists():
        allowed_ids = set()
        with candidate_manifest.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                allowed_ids.add(json.loads(line)["document_id"])

    ensure_dir(output_dir)
    jsonl_path = output_dir / "gold_candidates_prefill.jsonl"
    csv_path = output_dir / "annotation_sheet.csv"

    records: list[dict] = []
    for per_doc_file in sorted(per_doc_dir.glob("*.json")):
        data = json.loads(per_doc_file.read_text(encoding="utf-8"))
        if allowed_ids is not None and data.get("document_id") not in allowed_ids:
            continue
        records.append(build_prefill_record(data))

    with jsonl_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"_banner": BANNER_COMMENT}, ensure_ascii=False) + "\n")
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        # Banner row (sits just under the header so it can't be silently skipped)
        banner_row = {field: "" for field in FIELDS}
        banner_row["document_id"] = "# BANNER"
        banner_row["filename"] = BANNER_COMMENT
        writer.writerow(banner_row)
        for record in records:
            writer.writerow(record)

    return jsonl_path, csv_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a preannotated gold candidate review pack.")
    parser.add_argument("--run-dir", required=True, help="Path to a batch-run directory (data/batch_runs/<ts>).")
    parser.add_argument(
        "--candidate-manifest",
        default=str(DEFAULT_GOLD_CANDIDATES_DIR / "gold_candidates_manifest.jsonl"),
        help="Restrict the pack to these candidates (default: gold_candidates_manifest.jsonl).",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_GOLD_CANDIDATES_DIR),
    )
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        # Accept "<timestamp>" as shorthand under the default batch dir.
        alt = DEFAULT_BATCH_RUNS_DIR / run_dir.name
        if alt.exists():
            run_dir = alt
        else:
            print(f"[error] run dir not found: {args.run_dir}", file=sys.stderr)
            return 2

    candidate_manifest = Path(args.candidate_manifest) if args.candidate_manifest else None
    if candidate_manifest is not None and not candidate_manifest.exists():
        print(f"[warn] candidate manifest missing: {candidate_manifest}; including all per_document files.")
        candidate_manifest = None

    jsonl_path, csv_path = run(run_dir, candidate_manifest, Path(args.output_dir))
    print(f"[ok] wrote {jsonl_path}")
    print(f"[ok] wrote {csv_path}")
    print("[remember] these outputs are PREANNOTATED — NOT VERIFIED — REQUIRES HUMAN REVIEW.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
