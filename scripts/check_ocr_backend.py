"""Offline Tesseract OCR probe (legacy / evaluation only).

This script is NOT part of the QualiFlow application runtime. It is a
standalone utility for offline experiments against saved Stage 4 cell crops.
Running it requires an installed Tesseract binary plus the optional
``pytesseract`` Python package; neither is needed by the main app or the
default test suite.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from app.config import settings
from app.services.ocr_service import run_ocr_from_table_parsing

COLUMN_TO_FIELD = {
    0: "item_id",
    1: "heat_number",
    2: "grade",
    3: "weight_or_length",
    4: "yield_strength_mpa",
    5: "tensile_strength_mpa",
    6: "elongation_percentage",
}


def _extract_column_index(path: Path) -> int | None:
    match = re.search(r"_c(\d+)\.png$", path.name, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _build_meta_from_samples(samples: list[Path]) -> dict:
    cell_crops = []
    for path in samples:
        col = _extract_column_index(path)
        cell_crops.append(
            {
                "row_index": 1,
                "column_index": int(col or 0),
                "canonical_field": COLUMN_TO_FIELD.get(int(col or -1), "heat_number"),
                "image_path": str(path),
            }
        )
    return {"pages": [{"page": 1, "table_parsing": {"cell_crops": cell_crops}}]}


def _pick_samples(limit: int, preferred_fields: list[str]) -> list[Path]:
    artifacts_dir = settings.storage_dir / "artifacts"
    all_cells = sorted(artifacts_dir.rglob("p*_cells/*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not all_cells:
        return []

    preferred_set = set(preferred_fields)
    preferred: list[Path] = []
    others: list[Path] = []
    for cell in all_cells:
        col = _extract_column_index(cell)
        field = COLUMN_TO_FIELD.get(col or -1)
        if field in preferred_set:
            preferred.append(cell)
        else:
            others.append(cell)
    merged = preferred + others
    return merged[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test OCR backend against saved Stage 4 cell crops.")
    parser.add_argument("--limit", type=int, default=8, help="How many crop images to test.")
    parser.add_argument(
        "--preferred-fields",
        nargs="*",
        default=["heat_number", "tensile_strength_mpa"],
        help="Field names to prioritize when selecting sample crops.",
    )
    parser.add_argument("--json", action="store_true", help="Print raw JSON result.")
    args = parser.parse_args()

    samples = _pick_samples(limit=max(1, args.limit), preferred_fields=args.preferred_fields)
    if not samples:
        print(f"No cell crops found under: {settings.storage_dir / 'artifacts'}")
        print("Run one extraction first so Stage 4 generates p*_cells/*.png artifacts.")
        return 1

    print(f"Using {len(samples)} sample crops from artifacts.")
    meta = _build_meta_from_samples(samples)
    result = run_ocr_from_table_parsing(meta)

    diagnostics = result.backend_diagnostics
    print("\n=== OCR Backend Diagnostics ===")
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))

    print("\n=== OCR Sample Results ===")
    non_empty = 0
    for cell in result.cell_results:
        if (cell.raw_text or "").strip():
            non_empty += 1
        print(
            json.dumps(
                {
                    "image_path": cell.image_path,
                    "field": cell.canonical_field,
                    "raw_text": cell.raw_text,
                    "normalized_text": cell.normalized_text,
                    "parsed_value": cell.parsed_value,
                    "ocr_confidence": cell.ocr_confidence,
                    "unresolved": cell.unresolved,
                    "unresolved_reason": cell.unresolved_reason,
                },
                ensure_ascii=False,
            )
        )

    print("\n=== Summary ===")
    print(
        json.dumps(
            {
                "backend": result.backend,
                "backend_available": result.backend_available,
                "sample_cells": len(result.cell_results),
                "non_empty_ocr_results": non_empty,
                "resolved_cells": result.resolved_count,
                "unresolved_cells": result.unresolved_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if args.json:
        print("\n=== Raw OCRRunResult JSON ===")
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
