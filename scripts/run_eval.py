"""Run QualiFlow gold-set evaluation.

Workflow:
1. Read ``data/gold/metadata_20.csv`` (or ``--metadata`` override).
2. Generate real predictions with an adapter when the extraction pipeline is
   callable and source PDFs are available.
3. Save predictions to ``outputs/predictions/<doc_id>.json``.
4. Run ``scripts.evaluate_outputs``.
5. Print a concise metric summary.

No prediction values are fabricated. If the real pipeline cannot be called, the
``MockExtractionAdapter`` documents the integration point and produces no
prediction file.

Real pipeline connection point:
``ExistingPipelineAdapter.predict`` currently calls the same internal helper
used by ``scripts.run_batch_extraction``: ``_run_single``. If QualiFlow later
exposes a cleaner service-level function such as ``extract_pdf_to_json(path)``,
replace that call inside ``ExistingPipelineAdapter.predict`` and keep this
runner unchanged.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_outputs import run_academic_evaluation


def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read_metadata(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "doc_id",
            "file_name",
            "quality_bucket",
            "document_type",
            "pages",
            "has_text_layer",
            "ground_truth_path",
        }
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"metadata missing required columns: {', '.join(sorted(missing))}")
        return [row for row in reader if (row.get("doc_id") or "").strip()]


def _resolve_document_path(row: dict[str, str], documents_root: Path | None) -> Path | None:
    file_name = (row.get("file_name") or "").strip()
    if not file_name:
        return None
    path = Path(file_name)
    if path.is_absolute():
        return path
    if documents_root is not None:
        return documents_root / path
    return None


class ExtractionAdapter(Protocol):
    name: str

    def predict(self, row: dict[str, str], pdf_path: Path) -> dict[str, Any] | None:
        """Return a real prediction payload, or ``None`` when unavailable."""


@dataclass
class MockExtractionAdapter:
    """No-op adapter for environments where the real pipeline is not callable.

    Connect the real pipeline by implementing ``predict`` with a call that
    returns the same kind of JSON written by the API or batch extractor. This
    adapter intentionally returns ``None`` so evaluation can report missing
    predictions without inventing values.
    """

    name: str = "mock"

    def predict(self, row: dict[str, str], pdf_path: Path) -> dict[str, Any] | None:
        return None


@dataclass
class ExistingPipelineAdapter:
    """Adapter around the current QualiFlow batch extraction helper."""

    mode: str = "D"
    force_route: str | None = None
    name: str = "existing"

    def predict(self, row: dict[str, str], pdf_path: Path) -> dict[str, Any] | None:
        try:
            from app.services.batch_policy import BatchRunPolicy
            from scripts.run_batch_extraction import _run_single
        except Exception as exc:  # noqa: BLE001 - dependency availability is environment-specific.
            print(f"[warn] real pipeline adapter unavailable: {exc}", file=sys.stderr)
            return None

        batch_row = {
            "document_id": row["doc_id"],
            "filename": row.get("file_name") or pdf_path.name,
            "abs_path": str(pdf_path.resolve()),
            "sha256": row["doc_id"],
        }
        policy = BatchRunPolicy.from_env()
        _summary, per_document, error = _run_single(
            batch_row,
            mode=self.mode,
            force_route=self.force_route,
            dry_run=False,
            policy=policy,
        )
        if error:
            print(f"[warn] extraction failed for {row['doc_id']}: {error}", file=sys.stderr)
            return None
        return per_document


def _adapter_from_name(name: str) -> ExtractionAdapter:
    if name == "mock":
        return MockExtractionAdapter()
    if name == "existing":
        return ExistingPipelineAdapter()
    raise ValueError(f"unknown adapter: {name}")


def _write_prediction(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _print_summary(summary: dict[str, Any], out_dir: Path, predictions_dir: Path) -> None:
    wanted = [
        "n_documents",
        "field_accuracy",
        "critical_field_accuracy",
        "document_type_accuracy",
        "processing_decision_accuracy",
        "review_rate",
        "unsafe_auto_accept_rate",
        "missing_required_field_rate",
        "average_latency_ms",
    ]
    print("\nEvaluation summary")
    print("------------------")
    for key in wanted:
        if key in summary and summary[key] != "":
            print(f"{key}: {summary[key]}")
    print(f"predictions: {predictions_dir}")
    print(f"eval_outputs: {out_dir}")


def run(
    *,
    metadata_path: Path,
    documents_root: Path | None,
    predictions_dir: Path,
    out_dir: Path,
    adapter: ExtractionAdapter,
    reuse_predictions: bool,
) -> dict[str, Any]:
    rows = _read_metadata(metadata_path)
    predictions_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    reused = 0
    skipped = 0

    for row in rows:
        doc_id = row["doc_id"].strip()
        pred_path = predictions_dir / f"{doc_id}.json"
        if reuse_predictions and pred_path.exists():
            reused += 1
            continue

        pdf_path = _resolve_document_path(row, documents_root)
        if pdf_path is None:
            print(f"[skip] {doc_id}: no --documents-root and file_name is not absolute")
            skipped += 1
            continue
        if not pdf_path.exists():
            print(f"[skip] {doc_id}: source PDF not found: {pdf_path}")
            skipped += 1
            continue

        prediction = adapter.predict(row, pdf_path)
        if prediction is None:
            print(f"[skip] {doc_id}: adapter '{adapter.name}' produced no prediction")
            skipped += 1
            continue

        _write_prediction(pred_path, prediction)
        generated += 1
        print(f"[ok] wrote prediction: {pred_path}")

    print(
        f"[info] prediction generation complete: generated={generated} reused={reused} skipped={skipped}"
    )
    summary = run_academic_evaluation(
        metadata_path=metadata_path,
        predictions_dir=predictions_dir,
        out_dir=out_dir,
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate predictions and evaluate the QualiFlow gold set.")
    parser.add_argument("--metadata", default="data/gold/metadata_20.csv")
    parser.add_argument(
        "--documents-root",
        default=None,
        help="Directory containing source PDFs. Required when metadata file_name values are relative.",
    )
    parser.add_argument("--predictions", default="outputs/predictions")
    parser.add_argument("--out", default=None, help="Defaults to outputs/eval_runs/<timestamp>.")
    parser.add_argument(
        "--adapter",
        choices=["existing", "mock"],
        default="existing",
        help="Use 'existing' for the current QualiFlow pipeline, or 'mock' as a documented no-op.",
    )
    parser.add_argument(
        "--no-reuse-predictions",
        action="store_true",
        help="Regenerate predictions even when outputs/predictions/<doc_id>.json already exists.",
    )
    args = parser.parse_args(argv)

    metadata_path = Path(args.metadata)
    predictions_dir = Path(args.predictions)
    out_dir = Path(args.out) if args.out else Path("outputs") / "eval_runs" / _utc_ts()
    documents_root = Path(args.documents_root) if args.documents_root else None

    if not metadata_path.exists():
        print(f"[error] metadata not found: {metadata_path}", file=sys.stderr)
        return 2

    try:
        adapter = _adapter_from_name(args.adapter)
        summary = run(
            metadata_path=metadata_path,
            documents_root=documents_root,
            predictions_dir=predictions_dir,
            out_dir=out_dir,
            adapter=adapter,
            reuse_predictions=not args.no_reuse_predictions,
        )
    except Exception as exc:
        print(f"[error] run_eval failed: {exc}", file=sys.stderr)
        return 1

    _print_summary(summary, out_dir, predictions_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
