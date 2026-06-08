"""Flatten one or more evaluation runs into a single thesis-ready summary.

Reads ``metrics.json`` files under ``data/eval_outputs/<ts>_mode_*/`` and emits
``eval_summary.md`` + ``eval_summary.csv`` at a configurable root.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from scripts._dataset_common import DEFAULT_EVAL_DIR, ensure_dir


def discover_eval_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        [path for path in root.iterdir() if path.is_dir() and (path / "metrics.json").exists()]
    )


def load_metrics(eval_dir: Path) -> dict | None:
    metrics_path = eval_dir / "metrics.json"
    if not metrics_path.exists():
        return None
    try:
        return json.loads(metrics_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def run(eval_root: Path, output_dir: Path) -> tuple[Path, Path]:
    ensure_dir(output_dir)
    rows: list[dict] = []
    for eval_dir in discover_eval_dirs(eval_root):
        payload = load_metrics(eval_dir)
        if payload is None:
            continue
        aggregate = payload.get("aggregate", {})
        rows.append(
            {
                "eval_dir": eval_dir.name,
                "mode": payload.get("mode"),
                "provisional": payload.get("provisional"),
                "documents_evaluated": payload.get("documents_evaluated"),
                **aggregate,
            }
        )

    fieldnames = [
        "eval_dir",
        "mode",
        "provisional",
        "documents_evaluated",
        "n",
        "field_accuracy",
        "critical_field_accuracy",
        "compliance_decision_accuracy",
        "review_rate",
        "stp_rate",
        "average_latency_ms",
        "p95_latency_ms",
        "extraction_completeness",
    ]
    summary_csv = output_dir / "eval_summary.csv"
    with summary_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    md_lines = [
        "# QualiFlow evaluation summary",
        "",
        "One row per evaluation run. A `provisional: true` row means the gold file",
        "was a preannotated candidate pack and still requires human verification.",
        "",
        "| eval_dir | mode | provisional | n | field_acc | crit_acc | compliance_acc | review_rate | stp_rate | avg_latency_ms | p95_latency_ms | completeness |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        md_lines.append(
            "| {eval_dir} | {mode} | {provisional} | {n} | {field_accuracy} | {critical_field_accuracy} | {compliance_decision_accuracy} | {review_rate} | {stp_rate} | {average_latency_ms} | {p95_latency_ms} | {extraction_completeness} |".format(
                **{**{key: row.get(key, "") for key in fieldnames}}
            )
        )
    summary_md = output_dir / "eval_summary.md"
    summary_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return summary_md, summary_csv


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flatten eval runs into a single summary.")
    parser.add_argument(
        "--eval-root",
        default=str(DEFAULT_EVAL_DIR),
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_EVAL_DIR),
    )
    args = parser.parse_args(argv)

    eval_root = Path(args.eval_root)
    if not eval_root.exists():
        print(f"[error] eval root not found: {eval_root}", file=sys.stderr)
        return 2

    md_path, csv_path = run(eval_root, Path(args.output_dir))
    print(f"[ok] wrote {md_path}")
    print(f"[ok] wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
