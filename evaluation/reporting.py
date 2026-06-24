"""Evaluation report writers for JSON, CSV, and Markdown."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from evaluation.metrics import EvaluationAggregate, FieldMatchResult


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def field_results_to_rows(results: list[FieldMatchResult], *, doc_id: str = "", quality_bucket: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        payload = result.to_dict()
        payload["doc_id"] = doc_id
        payload["quality_bucket"] = quality_bucket
        rows.append(payload)
    return rows


def aggregate_to_summary_dict(aggregate: EvaluationAggregate) -> dict[str, Any]:
    return {
        "n_comparisons": aggregate.n_comparisons,
        "raw_exact_accuracy": aggregate.raw_exact_accuracy,
        "business_normalized_accuracy": aggregate.business_normalized_accuracy,
        "accuracy_delta": aggregate.accuracy_delta,
        "harmless_normalization_accepts": aggregate.harmless_normalization_accepts,
        "true_mismatches": aggregate.true_mismatches,
        "review_needed": aggregate.review_needed,
        "critical_identifier_mismatches": aggregate.critical_identifier_mismatches,
        "matcher_used": aggregate.matcher_used,
        "per_field_raw_accuracy": aggregate.per_field_raw,
        "per_field_business_accuracy": aggregate.per_field_business,
    }


def write_evaluation_outputs(
    *,
    out_dir: Path,
    aggregate: EvaluationAggregate,
    field_rows: list[dict[str, Any]],
    legacy_summary: dict[str, Any],
    metadata_path: Path,
    predictions_dir: Path,
    output_json: Path | None = None,
    output_csv: Path | None = None,
    output_md: Path | None = None,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    summary = aggregate_to_summary_dict(aggregate)
    merged_summary = {**legacy_summary, **summary}

    json_path = output_json or out_dir / "metrics.json"
    json_payload = {
        "metadata_path": str(metadata_path),
        "predictions_dir": str(predictions_dir),
        "legacy": legacy_summary,
        "evaluation_layer": summary,
        "examples": {
            "raw_fail_business_pass": [row.to_dict() for row in aggregate.examples_raw_fail_business_pass],
            "both_fail": [row.to_dict() for row in aggregate.examples_both_fail],
            "critical_fail": [row.to_dict() for row in aggregate.examples_critical_fail],
        },
    }
    json_path.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    written["json"] = json_path

    csv_path = output_csv or out_dir / "field_comparisons.csv"
    if field_rows:
        fieldnames = list(field_rows[0].keys())
        _write_csv(csv_path, fieldnames, field_rows)
        written["csv"] = csv_path

    per_field_rows = [
        {
            "field": field,
            "raw_exact_accuracy": aggregate.per_field_raw.get(field, ""),
            "business_normalized_accuracy": aggregate.per_field_business.get(field, ""),
            "delta": round(
                aggregate.per_field_business.get(field, 0.0) - aggregate.per_field_raw.get(field, 0.0),
                4,
            ),
        }
        for field in sorted(set(aggregate.per_field_raw) | set(aggregate.per_field_business))
    ]
    _write_csv(
        out_dir / "metrics_by_field_enhanced.csv",
        ["field", "raw_exact_accuracy", "business_normalized_accuracy", "delta"],
        per_field_rows,
    )
    written["per_field_csv"] = out_dir / "metrics_by_field_enhanced.csv"

    matcher_rows = [{"matcher_used": key, "count": value} for key, value in sorted(aggregate.matcher_used.items())]
    _write_csv(out_dir / "matcher_breakdown.csv", ["matcher_used", "count"], matcher_rows)
    written["matcher_csv"] = out_dir / "matcher_breakdown.csv"

    md_path = output_md or out_dir / "eval_report_enhanced.md"
    md_lines = [
        "# QualiFlow Evaluation Report (Enhanced Layer)",
        "",
        f"- metadata: `{metadata_path}`",
        f"- predictions: `{predictions_dir}`",
        "",
        "## Accuracy Metrics",
        "",
        "| metric | value |",
        "| --- | --- |",
    ]
    for key in (
        "raw_exact_accuracy",
        "business_normalized_accuracy",
        "accuracy_delta",
        "harmless_normalization_accepts",
        "true_mismatches",
        "review_needed",
        "critical_identifier_mismatches",
    ):
        md_lines.append(f"| {key} | {merged_summary.get(key, '')} |")
    md_lines.extend(
        [
            "",
            "## Legacy Metrics (backward compatible)",
            "",
            "| metric | value |",
            "| --- | --- |",
        ]
    )
    for key, value in legacy_summary.items():
        md_lines.append(f"| {key} | {value} |")
    md_lines.extend(
        [
            "",
            "## Matcher Breakdown",
            "",
            "| matcher | count |",
            "| --- | --- |",
        ]
    )
    for row in matcher_rows:
        md_lines.append(f"| {row['matcher_used']} | {row['count']} |")
    md_lines.extend(
        [
            "",
            "## Examples: raw fail, business pass",
            "",
        ]
    )
    for example in aggregate.examples_raw_fail_business_pass:
        md_lines.append(
            f"- `{example.field}` gold=`{example.gold_raw}` pred=`{example.pred_raw}` "
            f"matcher=`{example.matcher_used}` reason=`{example.reason}`"
        )
    if not aggregate.examples_raw_fail_business_pass:
        md_lines.append("- (none)")
    md_lines.extend(["", "## Examples: both fail", ""])
    for example in aggregate.examples_both_fail:
        md_lines.append(
            f"- `{example.field}` gold=`{example.gold_raw}` pred=`{example.pred_raw}` reason=`{example.reason}`"
        )
    if not aggregate.examples_both_fail:
        md_lines.append("- (none)")
    md_lines.extend(["", "## Examples: critical identifier failures", ""])
    for example in aggregate.examples_critical_fail:
        md_lines.append(
            f"- `{example.field}` gold=`{example.gold_raw}` pred=`{example.pred_raw}` reason=`{example.reason}`"
        )
    if not aggregate.examples_critical_fail:
        md_lines.append("- (none)")
    md_lines.extend(
        [
            "",
            "## Method",
            "",
            "The evaluation layer reports both `raw_exact_accuracy` (literal string equality) and "
            "`business_normalized_accuracy` (field-aware deterministic matchers). "
            "Critical identifiers use strict matching only. "
            "This measures evaluation quality and extraction comparability — not model safety routing.",
            "",
        ]
    )
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    written["md"] = md_path

    _write_csv(out_dir / "metrics_summary_enhanced.csv", list(merged_summary.keys()), [merged_summary])
    written["summary_csv"] = out_dir / "metrics_summary_enhanced.csv"
    return written
