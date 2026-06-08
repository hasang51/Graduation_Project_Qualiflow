"""Merge ``per_document/*.json`` artefacts from multiple batch runs.

Rebuilds ``summary.csv`` / ``summary.json`` from the merged folder and merges
``usage.csv`` rows when those files exist on the source runs.

Example::

    python -m scripts.merge_batch_runs --output data/batch_runs/final20_full \\
        --take data/batch_runs/final20 doc001 doc002 doc003 doc004 doc005 \\
        --take data/batch_runs/final20_remaining doc006 doc007 doc008 doc009 \\
            doc010 doc011 doc012 doc013 doc014 doc015 doc016 doc017 doc018 \\
            doc019 doc020
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

from scripts.run_batch_extraction import SUMMARY_FIELDS, _aggregate, _flatten_summary_row


def _natural_doc_sort_key(doc_id: str) -> int:
    prefix = "doc"
    if doc_id.startswith(prefix):
        try:
            return int(doc_id[len(prefix) :])
        except ValueError:
            pass
    return hash(doc_id)


def _per_document_to_summary_row(cached: dict, *, mode_fallback: str = "D") -> dict:
    extraction_dict = cached.get("extraction") or {}
    review_dict = cached.get("review_policy") or {}
    llm_usage = cached.get("llm_usage") or {}
    return _flatten_summary_row(
        document_id=str(cached.get("document_id") or ""),
        filename=str(cached.get("filename") or ""),
        quality_class=(cached.get("profile") or {}).get("quality_class"),
        route_used=cached.get("route_used"),
        page_count=(cached.get("profile") or {}).get("page_count"),
        mode=str(cached.get("mode") or mode_fallback),
        extraction={**extraction_dict, "llm_usage": llm_usage},
        review=review_dict,
        latency_ms=float(cached.get("latency_ms") or 0.0),
        status="OK",
        error=None,
    )


def _load_usage_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(dict(row))
    return rows


def _merge_policy_summaries(paths: list[Path]) -> dict:
    total_in = 0
    total_out = 0
    total_live = 0
    rl = 0
    for p in paths:
        if not p.is_file():
            continue
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        ps = payload.get("policy_summary") or {}
        total_in += int(ps.get("total_input_tokens") or 0)
        total_out += int(ps.get("total_output_tokens") or 0)
        total_live += int(ps.get("total_new_live_docs") or 0)
        rl += int(ps.get("rate_limit_events") or 0)
    estimated = round(total_in / 1000.0 * 0.003 + total_out / 1000.0 * 0.015, 6)
    return {
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_new_live_docs": total_live,
        "rate_limit_events": rl,
        "estimated_spend_usd": estimated,
    }


def merge(
    *,
    output_dir: Path,
    segments: list[tuple[Path, list[str]]],
    mode_fallback: str = "D",
) -> Path:
    """Copy listed documents into ``output_dir/per_document`` and rebuild summaries."""

    assignments: dict[str, Path] = {}
    source_roots: list[Path] = []
    missing_assignments: list[str] = []

    for run_root, doc_ids in segments:
        run_root = run_root.resolve()
        source_roots.append(run_root)
        per_doc = run_root / "per_document"
        if not per_doc.is_dir():
            print(f"[error] missing per_document/: {per_doc}", file=sys.stderr)
            sys.exit(2)
        for doc_id in doc_ids:
            if doc_id in assignments:
                print(f"[error] duplicate doc_id in --take segments: {doc_id}", file=sys.stderr)
                sys.exit(2)
            assignments[doc_id] = per_doc

    out_root = output_dir.resolve()
    out_per = out_root / "per_document"
    out_root.mkdir(parents=True, exist_ok=True)
    out_per.mkdir(parents=True, exist_ok=True)

    sorted_ids = sorted(assignments.keys(), key=_natural_doc_sort_key)
    for doc_id in sorted_ids:
        src_json = assignments[doc_id] / f"{doc_id}.json"
        if not src_json.is_file():
            missing_assignments.append(doc_id)
            continue
        shutil.copy2(src_json, out_per / f"{doc_id}.json")

    if missing_assignments:
        print(
            "[error] missing per-document JSON for: " + ", ".join(sorted(missing_assignments, key=_natural_doc_sort_key)),
            file=sys.stderr,
        )
        sys.exit(3)

    summary_rows: list[dict] = []
    for doc_id in sorted_ids:
        cached = json.loads((out_per / f"{doc_id}.json").read_text(encoding="utf-8"))
        summary_rows.append(_per_document_to_summary_row(cached, mode_fallback=mode_fallback))

    summary_csv_path = out_root / "summary.csv"
    with summary_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in summary_rows:
            writer.writerow(row)

    aggregate = _aggregate(summary_rows)
    summary_json_sources = [r / "summary.json" for r in source_roots]
    policy_summary = _merge_policy_summaries(summary_json_sources)

    src_detail = [{"run_dir": str(run_root.resolve()), "documents": list(doc_ids)} for run_root, doc_ids in segments]
    config = {
        "merge_tool": "scripts.merge_batch_runs",
        "output_dir": str(out_root),
        "sources": src_detail,
    }

    summary_json_path = out_root / "summary.json"
    summary_json_path.write_text(
        json.dumps(
            {"config": config, "aggregate": aggregate, "policy_summary": policy_summary},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    usage_fields = ["document_id", "filename", "input_tokens", "output_tokens", "pages_sent", "estimated_cost_usd", "latency_ms"]
    merged_usage: list[dict[str, str]] = []
    seen_usage_ids: set[str] = set()
    for run_root, doc_ids in segments:
        rows = _load_usage_rows(run_root / "usage.csv")
        want = set(doc_ids)
        for row in rows:
            did = (row.get("document_id") or "").strip()
            if did in want and did not in seen_usage_ids:
                merged_usage.append(row)
                seen_usage_ids.add(did)

    usage_csv_path = out_root / "usage.csv"
    if merged_usage:
        with usage_csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=usage_fields, extrasaction="ignore")
            writer.writeheader()
            for row in sorted(merged_usage, key=lambda r: _natural_doc_sort_key(r.get("document_id") or "")):
                writer.writerow(row)

    return out_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Merge batch run per_document outputs into one folder and rebuild summaries.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination run directory (will contain per_document/, summary.csv, summary.json).",
    )
    parser.add_argument(
        "--take",
        dest="takes",
        action="append",
        nargs="+",
        metavar=("RUN_DIR", "DOC_ID"),
        required=True,
        help="Run directory followed by one or more document_id values (repeatable).",
    )
    parser.add_argument(
        "--mode-fallback",
        default="D",
        help="Mode string stored in summary rows when per-document JSON omits mode (default: D).",
    )
    args = parser.parse_args(argv)

    segments: list[tuple[Path, list[str]]] = []
    for chunk in args.takes:
        if len(chunk) < 2:
            print("[error] each --take needs RUN_DIR and at least one DOC_ID", file=sys.stderr)
            return 2
        run_dir = Path(chunk[0])
        doc_ids = [d.strip() for d in chunk[1:] if d.strip()]
        if not doc_ids:
            print("[error] each --take needs at least one DOC_ID", file=sys.stderr)
            return 2
        segments.append((run_dir, doc_ids))

    out = merge(output_dir=args.output, segments=segments, mode_fallback=args.mode_fallback)
    print(f"[ok] merged batch outputs -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
