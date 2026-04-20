"""Detect and normalise verified gold annotations.

Mode A — verified gold exists::

    data/gold_verified/annotations.jsonl    (one JSON object per document)
    data/gold_verified/annotations.csv      (same data flattened)

If either of these files is present, normalise it into
``data/gold_verified/gold_manifest.jsonl`` / ``gold_manifest.csv``. Each
record includes the canonical truth for:
- supplier_name
- document_type
- certificate_date
- is_compliant
- heat_numbers (pipe list)
- grades (pipe list)
- yield_strength_mpa (pipe list of floats)
- tensile_strength_mpa (pipe list of floats)
- elongation_percentage (pipe list of floats)

Mode B — verified gold does NOT exist:
Prints a clear warning pointing to the preannotated candidate workflow.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from scripts._dataset_common import DEFAULT_GOLD_VERIFIED_DIR, ensure_dir

EXPECTED_FIELDS = [
    "document_id",
    "filename",
    "supplier_name",
    "document_type",
    "certificate_date",
    "is_compliant",
    "heat_numbers",
    "grades",
    "yield_strength_mpa",
    "tensile_strength_mpa",
    "elongation_percentage",
    "notes",
]


def _split_pipe(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    return [chunk.strip() for chunk in str(value).split("|") if chunk.strip()]


def _parse_bool(value: object) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    token = str(value).strip().lower()
    if token in {"1", "true", "yes", "y", "compliant", "pass"}:
        return True
    if token in {"0", "false", "no", "n", "non_compliant", "fail"}:
        return False
    return None


def _normalise_record(raw: dict) -> dict:
    return {
        "document_id": raw.get("document_id") or raw.get("doc_id"),
        "filename": raw.get("filename"),
        "supplier_name": (raw.get("supplier_name") or "").strip() or None,
        "document_type": (raw.get("document_type") or "").strip() or None,
        "certificate_date": (raw.get("certificate_date") or "").strip() or None,
        "is_compliant": _parse_bool(raw.get("is_compliant")),
        "heat_numbers": _split_pipe(raw.get("heat_numbers")),
        "grades": _split_pipe(raw.get("grades")),
        "yield_strength_mpa": _split_pipe(raw.get("yield_strength_mpa")),
        "tensile_strength_mpa": _split_pipe(raw.get("tensile_strength_mpa")),
        "elongation_percentage": _split_pipe(raw.get("elongation_percentage")),
        "notes": raw.get("notes") or "",
    }


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def run(gold_dir: Path) -> tuple[bool, list[dict]]:
    jsonl_path = gold_dir / "annotations.jsonl"
    csv_path = gold_dir / "annotations.csv"

    if jsonl_path.exists():
        raw = _load_jsonl(jsonl_path)
        print(f"[ok] detected verified gold (jsonl): {jsonl_path}")
    elif csv_path.exists():
        raw = _load_csv(csv_path)
        print(f"[ok] detected verified gold (csv): {csv_path}")
    else:
        return False, []

    normalised = [_normalise_record(row) for row in raw]
    return True, normalised


def write_outputs(records: list[dict], output_dir: Path) -> tuple[Path, Path]:
    ensure_dir(output_dir)
    jsonl_path = output_dir / "gold_manifest.jsonl"
    csv_path = output_dir / "gold_manifest.csv"

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPECTED_FIELDS)
        writer.writeheader()
        for rec in records:
            flat = dict(rec)
            for key in ("heat_numbers", "grades", "yield_strength_mpa", "tensile_strength_mpa", "elongation_percentage"):
                flat[key] = "|".join(flat.get(key) or [])
            writer.writerow(flat)

    return jsonl_path, csv_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect & normalise verified gold (Mode A) or print Mode B warning.")
    parser.add_argument("--gold-dir", default=str(DEFAULT_GOLD_VERIFIED_DIR))
    args = parser.parse_args(argv)

    gold_dir = Path(args.gold_dir)
    ensure_dir(gold_dir)

    found, records = run(gold_dir)
    if not found:
        print("[mode_b] No verified gold found in", gold_dir)
        print("[mode_b] Use the preannotated candidate workflow instead:")
        print("         1. python -m scripts.select_gold_candidates --n 20")
        print("         2. python -m scripts.run_batch_extraction --subset data/gold_candidates/gold_candidates_manifest.jsonl")
        print("         3. python -m scripts.build_prefill_pack --run-dir <batch_timestamp>")
        print("         4. review data/gold_candidates/annotation_sheet.csv manually")
        print("         5. drop the verified annotations into data/gold_verified/annotations.(jsonl|csv)")
        print("         6. rerun this script to normalise them into gold_manifest.(jsonl|csv)")
        return 1

    jsonl_path, csv_path = write_outputs(records, gold_dir)
    print(f"[ok] wrote {jsonl_path}")
    print(f"[ok] wrote {csv_path}")
    print(f"[ok] verified gold records: {len(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
