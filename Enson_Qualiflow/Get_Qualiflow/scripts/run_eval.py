"""Run the QualiFlow evaluation harness against a batch run.

Supports experiment modes:
- A — ``legacy_ocr_offline_baseline``: SKIPPED (cell-level OCR is offline only).
- B — ``multimodal_direct_no_routing``: compare batch run with ``--mode B``.
- C — ``multimodal_preprocessed_fixed``: compare batch run with ``--mode C``.
- D — ``routed_hybrid_proposed``: default; compare batch run with ``--mode D``.

If the gold file is a preannotated candidate file (has ``_banner`` marker or
``review_status`` column), evaluation still runs but metrics are flagged
``provisional: true`` in the output.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from scripts._dataset_common import (
    DEFAULT_EVAL_DIR,
    DEFAULT_GOLD_CANDIDATES_DIR,
    DEFAULT_GOLD_VERIFIED_DIR,
    ensure_dir,
)
from scripts.evaluate_outputs import (
    DocumentEvaluation,
    aggregate_metrics,
    evaluate_document,
)


def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_gold(gold_path: Path) -> tuple[dict[str, dict], bool]:
    """Return ``(records_by_document_id, provisional)``.

    ``provisional`` is True for preannotated candidate packs.
    """

    provisional = False
    rows = _load_jsonl(gold_path)
    cleaned: dict[str, dict] = {}
    for row in rows:
        if "_banner" in row:
            provisional = True
            continue
        if row.get("review_status") is not None and row.get("extracted_supplier_name") is not None:
            # This is an annotation_sheet-style preannotated row. Map to gold shape.
            provisional = True
            gold_like = {
                "document_id": row.get("document_id"),
                "filename": row.get("filename"),
                "supplier_name": row.get("verified_supplier_name") or row.get("extracted_supplier_name"),
                "document_type": row.get("verified_document_type") or row.get("extracted_document_type"),
                "certificate_date": row.get("verified_certificate_date") or row.get("extracted_certificate_date"),
                "is_compliant": row.get("verified_is_compliant") or row.get("extracted_is_compliant"),
                "heat_numbers": row.get("verified_heat_numbers") or row.get("extracted_heat_numbers"),
                "grades": row.get("verified_grades") or row.get("extracted_grades"),
                "yield_strength_mpa": row.get("verified_yield_strength_mpa") or row.get("extracted_yield_strength_mpa"),
                "tensile_strength_mpa": row.get("verified_tensile_strength_mpa") or row.get("extracted_tensile_strength_mpa"),
                "elongation_percentage": row.get("verified_elongation_percentage") or row.get("extracted_elongation_percentage"),
            }
            cleaned[gold_like["document_id"]] = gold_like
        else:
            cleaned[row["document_id"]] = row
    return cleaned, provisional


def _load_run(run_dir: Path) -> dict[str, dict]:
    per_doc_dir = run_dir / "per_document"
    if not per_doc_dir.exists():
        raise FileNotFoundError(f"No per_document/ under {run_dir}")
    results: dict[str, dict] = {}
    for per_doc_file in sorted(per_doc_dir.glob("*.json")):
        data = json.loads(per_doc_file.read_text(encoding="utf-8"))
        results[data["document_id"]] = data
    return results


def _comparisons_to_str(comparisons) -> str:
    tokens: list[str] = []
    for comp in comparisons:
        flag = "=" if comp.equal else "!"
        tokens.append(f"{comp.field}{flag}")
    return ",".join(tokens)


def run(
    *,
    gold_path: Path,
    run_dir: Path,
    mode: str,
    output_root: Path,
    provisional_override: bool,
) -> Path:
    if mode == "A":
        print("[skip] Experiment Mode A (legacy_ocr_offline_baseline) is not available.")
        print("       The repository keeps cell-level Tesseract OCR as an offline utility")
        print("       (app/services/ocr_service.py, scripts/check_ocr_backend.py). It is not")
        print("       a comparable end-to-end extraction engine — integrating it would require")
        print("       re-implementing row aggregation from cell crops. Run modes B, C, or D instead.")
        return output_root  # early exit — nothing written

    gold_by_id, is_provisional_gold = _load_gold(gold_path)
    if provisional_override:
        is_provisional_gold = True

    run_by_id = _load_run(run_dir)

    ts = _utc_ts()
    eval_dir = ensure_dir(output_root / f"{ts}_mode_{mode}")
    per_doc_csv = eval_dir / "per_document.csv"
    metrics_json = eval_dir / "metrics.json"
    report_md = eval_dir / "report.md"

    evaluations: list[DocumentEvaluation] = []
    missing: list[str] = []
    for doc_id, gold_record in gold_by_id.items():
        run_record = run_by_id.get(doc_id)
        if run_record is None:
            missing.append(doc_id)
            continue
        evaluations.append(evaluate_document(gold_record=gold_record, per_document=run_record))

    aggregate = aggregate_metrics(evaluations)

    with per_doc_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "document_id",
            "filename",
            "mode",
            "route_used",
            "quality_class",
            "field_accuracy",
            "critical_field_accuracy",
            "compliance_correct",
            "review_required",
            "latency_ms",
            "completeness",
            "comparisons",
        ])
        for ev in evaluations:
            field_acc = ev.field_hits / ev.field_total if ev.field_total else 0.0
            crit_acc = ev.critical_hits / ev.critical_total if ev.critical_total else 0.0
            writer.writerow([
                ev.document_id,
                ev.filename,
                ev.mode,
                ev.route_used,
                ev.quality_class,
                round(field_acc, 4),
                round(crit_acc, 4),
                ev.compliance_correct,
                ev.review_required,
                ev.latency_ms,
                ev.completeness,
                _comparisons_to_str(ev.comparisons),
            ])

    metrics_payload = {
        "timestamp": ts,
        "mode": mode,
        "run_dir": str(run_dir.resolve()),
        "gold_path": str(gold_path.resolve()),
        "provisional": bool(is_provisional_gold),
        "aggregate": aggregate,
        "documents_evaluated": len(evaluations),
        "documents_missing_in_run": missing,
    }
    metrics_json.write_text(json.dumps(metrics_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"# QualiFlow evaluation — mode {mode}",
        "",
        f"- timestamp: `{ts}`",
        f"- run_dir: `{run_dir}`",
        f"- gold_path: `{gold_path}`",
        f"- provisional: **{'YES — NOT VERIFIED GOLD' if is_provisional_gold else 'no — verified gold'}**",
        f"- documents evaluated: {len(evaluations)}",
        f"- documents missing in run: {len(missing)}",
        "",
        "## Aggregate metrics",
        "",
        "| metric | value |",
        "| --- | --- |",
    ]
    for key, value in aggregate.items():
        lines.append(f"| {key} | {value} |")
    if is_provisional_gold:
        lines.append("")
        lines.append(
            "> **PROVISIONAL**: these metrics are computed against a preannotated "
            "candidate set. They are not final thesis results. A reviewer must "
            "verify the annotation_sheet.csv before treating these numbers as "
            "authoritative."
        )
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[ok] wrote {per_doc_csv}")
    print(f"[ok] wrote {metrics_json}")
    print(f"[ok] wrote {report_md}")
    print(f"[ok] aggregate: {json.dumps(aggregate, indent=2)}")
    if is_provisional_gold:
        print("[warn] metrics are PROVISIONAL (preannotated gold — requires human review)")
    return eval_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run evaluation against a batch run.")
    parser.add_argument("--mode", choices=["A", "B", "C", "D"], default="D")
    parser.add_argument("--run-dir", required=False, default=None, help="Batch run directory.")
    parser.add_argument(
        "--gold",
        default=None,
        help="Path to gold jsonl (either verified or preannotated candidate).",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_EVAL_DIR),
    )
    parser.add_argument(
        "--provisional",
        action="store_true",
        help="Force the output to be flagged provisional regardless of source.",
    )
    args = parser.parse_args(argv)

    if args.mode == "A":
        # Early-exit call to run() to print the skip message.
        run(
            gold_path=Path(args.gold or "nonexistent.jsonl"),
            run_dir=Path(args.run_dir or "nonexistent"),
            mode="A",
            output_root=Path(args.output_root),
            provisional_override=False,
        )
        return 0

    if args.run_dir is None:
        print("[error] --run-dir is required for modes B/C/D", file=sys.stderr)
        return 2

    if args.gold is None:
        # Try default verified first, then candidate preannotated.
        candidates = [
            DEFAULT_GOLD_VERIFIED_DIR / "gold_manifest.jsonl",
            DEFAULT_GOLD_VERIFIED_DIR / "annotations.jsonl",
            DEFAULT_GOLD_CANDIDATES_DIR / "gold_candidates_prefill.jsonl",
        ]
        picked = next((c for c in candidates if c.exists()), None)
        if picked is None:
            print("[error] --gold not provided and no default gold file found", file=sys.stderr)
            return 2
        gold_path = picked
        print(f"[info] using default gold path: {gold_path}")
    else:
        gold_path = Path(args.gold)

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(f"[error] run dir not found: {run_dir}", file=sys.stderr)
        return 2
    if not gold_path.exists():
        print(f"[error] gold path not found: {gold_path}", file=sys.stderr)
        return 2

    run(
        gold_path=gold_path,
        run_dir=run_dir,
        mode=args.mode,
        output_root=Path(args.output_root),
        provisional_override=args.provisional,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
