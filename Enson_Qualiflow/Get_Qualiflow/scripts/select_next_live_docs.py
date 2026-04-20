"""Select the next cheapest N docs for live extraction from the candidate pool.

Selection objective
-------------------
1. Exclude docs already live-extracted (existing per-document JSONs).
2. Prefer short docs (1–2 pages) to minimise token cost.
3. Exclude severe-scan docs (blur_score < threshold) unless --include-severe.
4. Maintain diversity across quality buckets (digital_clean, scan_clean,
   scan_degraded).
5. Within budget, prefer docs with a strong relevance signal (text-dense or
   table-present).

Output
------
- ``data/gold_candidates/next_<N>_live_docs.{csv,jsonl}``

Each row includes:
- document_id, filename, quality_class, page_count
- selected_pages (integer — estimated pages to send)
- expected_cost_bucket (low / medium / high)
- reason_selected

Usage::

    python -m scripts.select_next_live_docs --n 5
    python -m scripts.select_next_live_docs --n 5 --include-severe
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

SEVERE_BLUR_THRESHOLD = 30.0


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _already_extracted(batch_runs_dir: Path) -> set[str]:
    """Return the set of document_ids that have a per-document JSON anywhere."""
    ids: set[str] = set()
    for run_dir in batch_runs_dir.iterdir():
        per_doc = run_dir / "per_document"
        if per_doc.exists():
            for f in per_doc.glob("*.json"):
                # The stem is the document_id.
                ids.add(f.stem)
    return ids


def _estimate_pages_to_send(row: dict, *, include_severe: bool) -> int:
    quality = row.get("quality_class", "scan_clean")
    page_count = int(row.get("page_count") or 1)
    if quality == "digital_clean":
        return min(page_count, 2)
    if quality == "scan_clean":
        return min(page_count, 2)
    if quality == "scan_degraded":
        return min(page_count, 3)
    return min(page_count, 2)


def _cost_bucket(est_pages: int) -> str:
    if est_pages <= 1:
        return "low"
    if est_pages <= 2:
        return "medium"
    return "high"


def _score(row: dict, *, include_severe: bool) -> float | None:
    """Return a desirability score, or None if the doc should be excluded."""
    quality = row.get("quality_class", "scan_clean")
    page_count = int(row.get("page_count") or 1)
    blur_score = float(row.get("blur_score") or 0.0)
    text_density = float(row.get("text_density") or 0.0)
    has_text_layer = bool(row.get("has_text_layer"))
    table_hint = bool(row.get("table_presence_hint"))

    # Exclude severe-scan docs unless explicitly included.
    if quality == "scan_degraded" and blur_score < SEVERE_BLUR_THRESHOLD and not include_severe:
        return None

    score = 0.0

    # Short docs cost fewer tokens.
    if page_count == 1:
        score += 50.0
    elif page_count == 2:
        score += 30.0
    elif page_count <= 4:
        score += 10.0
    else:
        score -= (page_count - 4) * 5.0  # penalise long docs

    # Diverse quality classes are valued.
    quality_bonus = {"digital_clean": 20.0, "scan_clean": 18.0, "scan_degraded": 15.0}
    score += quality_bonus.get(quality, 10.0)

    # Text layer and table presence are positive signals.
    if has_text_layer:
        score += 10.0
    if table_hint:
        score += 15.0
    score += text_density * 5.0

    # Penalise very blurry scans even if not "severe".
    if quality == "scan_degraded" and blur_score < 100:
        score -= 10.0

    return score


def _build_reason(row: dict, *, est_pages: int, include_severe: bool) -> str:
    parts = []
    page_count = int(row.get("page_count") or 1)
    quality = row.get("quality_class", "?")
    parts.append(f"quality={quality}")
    if page_count == 1:
        parts.append("single_page")
    parts.append(f"pages={page_count}")
    parts.append(f"send={est_pages}")
    blur = row.get("blur_score")
    if blur is not None:
        parts.append(f"blur={float(blur):.0f}")
    if row.get("has_text_layer"):
        parts.append("has_text")
    if row.get("table_presence_hint"):
        parts.append("table_hint")
    return ";".join(parts)


def select(
    candidates: list[dict],
    *,
    already_done: set[str],
    n: int,
    include_severe: bool,
) -> list[dict]:
    """Return up to ``n`` docs, balanced across quality buckets."""
    remaining = [r for r in candidates if r["document_id"] not in already_done]

    scored = []
    for row in remaining:
        s = _score(row, include_severe=include_severe)
        if s is not None:
            scored.append((s, row))

    scored.sort(key=lambda t: -t[0])

    # Greedy balanced pick: fill buckets in rotation.
    buckets: dict[str, list] = {"digital_clean": [], "scan_clean": [], "scan_degraded": []}
    for _, row in scored:
        q = row.get("quality_class", "scan_clean")
        buckets.setdefault(q, []).append(row)

    selected: list[dict] = []
    bucket_names = list(buckets.keys())
    i = 0
    while len(selected) < n:
        made_progress = False
        for bucket in bucket_names:
            if len(selected) >= n:
                break
            if buckets[bucket]:
                row = buckets[bucket].pop(0)
                est = _estimate_pages_to_send(row, include_severe=include_severe)
                row = dict(row)
                row["selected_pages"] = est
                row["expected_cost_bucket"] = _cost_bucket(est)
                row["reason_selected"] = _build_reason(row, est_pages=est, include_severe=include_severe)
                selected.append(row)
                made_progress = True
        i += 1
        if not made_progress or i > len(candidates):
            break

    return selected


OUTPUT_FIELDS = [
    "document_id",
    "filename",
    "quality_class",
    "page_count",
    "selected_pages",
    "expected_cost_bucket",
    "reason_selected",
    "abs_path",
]


def run(n: int, *, include_severe: bool, output_dir: Path, batch_runs_dir: Path) -> Path:
    candidate_path = DEFAULT_GOLD_CANDIDATES_DIR / "gold_candidates_manifest.jsonl"
    if not candidate_path.exists():
        raise FileNotFoundError(f"Candidate manifest not found: {candidate_path}")

    candidates = _load_jsonl(candidate_path)
    already_done = _already_extracted(batch_runs_dir)
    print(f"[info] {len(candidates)} candidates, {len(already_done)} already extracted")

    selected = select(candidates, already_done=already_done, n=n, include_severe=include_severe)
    print(f"[info] selected {len(selected)} docs for next live run")

    ensure_dir(output_dir)
    out_name = f"next_{n}_live_docs"
    csv_path = output_dir / f"{out_name}.csv"
    jsonl_path = output_dir / f"{out_name}.jsonl"

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in selected:
            writer.writerow(row)

    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in selected:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return csv_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select the next cheapest N docs for live extraction.")
    parser.add_argument("--n", type=int, default=5, help="Number of docs to select.")
    parser.add_argument(
        "--include-severe",
        action="store_true",
        help="Include severe-scan (very blurry) documents.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_GOLD_CANDIDATES_DIR),
    )
    parser.add_argument(
        "--batch-runs-dir",
        default=str(DEFAULT_BATCH_RUNS_DIR),
    )
    args = parser.parse_args(argv)

    csv_path = run(
        args.n,
        include_severe=args.include_severe,
        output_dir=Path(args.output_dir),
        batch_runs_dir=Path(args.batch_runs_dir),
    )
    print(f"[ok] wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
