# Dataset workflow — QualiFlow Phase 2

Phase 2 adds a reproducible dataset workflow on top of the unchanged runtime. Every step is a thin CLI script under `scripts/`; each produces structured artefacts under `data/` that the next step consumes.

## 1. Folder layout

```
data/
├── manifests/
│   ├── documents_discovery.jsonl   # one row per PDF: id, path, size, sha256
│   ├── documents_discovery.csv
│   ├── documents_manifest.jsonl    # discovery + profile (one row per PDF)
│   ├── documents_manifest.csv
│   ├── profile_summary.csv         # aggregate counts by quality_class
│   ├── manifest.jsonl              # canonical manifest with bucketing fields
│   └── manifest.csv
├── gold_candidates/
│   ├── gold_candidates_manifest.jsonl   # balanced candidate set (default N=20)
│   ├── gold_candidates_manifest.csv
│   ├── gold_candidates_prefill.jsonl    # model-generated pre-annotations
│   └── annotation_sheet.csv             # reviewer-friendly CSV (PREANNOTATED)
├── gold_verified/
│   ├── annotations.jsonl  # OPTIONAL — human-verified gold (Mode A input)
│   ├── annotations.csv
│   ├── gold_manifest.jsonl  # normalised by scripts.load_gold
│   └── gold_manifest.csv
├── batch_runs/<timestamp>/
│   ├── per_document/<document_id>.json
│   ├── summary.csv
│   ├── summary.json
│   ├── errors.jsonl
│   └── config.json
└── eval_outputs/<timestamp>_mode_<mode>/
    ├── metrics.json
    ├── per_document.csv
    └── report.md
```

## 2. Dataset root

The ~100 PDF corpus lives outside the repository. Scripts discover it in this order:

1. `--dataset-root` CLI flag;
2. `QUALIFLOW_DATASET_ROOT` environment variable;
3. the hard-coded default at `C:\Users\DELL\Downloads\Mill Test CertificateS\Mill Test CertificateS`.

## 3. Manifest schemas

### `documents_discovery.jsonl`

| field | description |
| --- | --- |
| `document_id` | `sha256(file)[:16]` |
| `filename` | base name |
| `abs_path` | absolute path inside the dataset root |
| `size_bytes` | file size |
| `sha256` | full SHA-256 hex |

### `documents_manifest.jsonl`

Same fields as discovery, plus every field on `DocumentProfile` (`page_count`, `has_text_layer`, `text_density`, `blur_score`, `noise_score`, `table_presence_hint`, `quality_class`, `reasons`).

### `manifest.jsonl`

Merges discovery + profile and adds bucketing fields:

| field | values |
| --- | --- |
| `page_bucket` | `single` (≤ 1), `short` (2–4), `long` (≥ 5) |
| `size_bucket` | `xs` (< 200 KB), `s` (< 1 MB), `m` (< 4 MB), `l` (< 12 MB), `xl` (≥ 12 MB) |
| `supplier_hint` | best-effort regex match on filename; falls back to `unknown` |

### `summary.csv` (batch run)

One row per document with at least:

- `document_id`, `filename`, `mode`, `route_used`, `quality_class`, `page_count`
- `status` (`OK`, `DRY_RUN`, `ERROR`), `extraction_status`, `validation_status`, `review_required`
- `confidence_score`, `raw_model_confidence`
- `total_items_detected`, `items_extracted`
- `missing_heat_numbers`, `missing_yield_values`, `missing_tensile_values`
- `structured_review_reasons`, `all_review_reasons`
- `latency_ms`, `error`

## 4. Gold workflow

Two modes, selected automatically by presence of verified annotations.

### Mode A — verified gold exists

Drop either `data/gold_verified/annotations.jsonl` or `annotations.csv` into the repo and run:

```bash
python -m scripts.load_gold
```

The script normalises columns, coerces booleans, splits pipe-delimited lists, and writes `gold_manifest.jsonl` / `gold_manifest.csv`. Evaluation with `--mode D` then consumes the normalised file and is **not** flagged provisional.

### Mode B — no verified gold yet

When no annotations are present, `scripts.load_gold` prints a clear warning and exits non-zero. Use the candidate workflow instead:

```bash
python -m scripts.select_gold_candidates --n 20
python -m scripts.run_batch_extraction --subset data/gold_candidates/gold_candidates_manifest.jsonl --mode D
python -m scripts.build_prefill_pack --run-dir data/batch_runs/<timestamp>
```

This produces `data/gold_candidates/annotation_sheet.csv` with a **PREANNOTATED — NOT VERIFIED — REQUIRES HUMAN REVIEW** banner row. A reviewer fills the `verified_*` columns manually, moves the accepted rows into `data/gold_verified/annotations.jsonl`, and reruns `scripts.load_gold` to produce the final verified gold.

Until that happens, any evaluation run using the prefill file is flagged `provisional: true` in `metrics.json`.

## 5. Batch extraction

```bash
python -m scripts.run_batch_extraction \
    --subset data/gold_candidates/gold_candidates_manifest.jsonl \
    --mode D
```

Per-document outputs include the full `UniversalDocumentExtraction` plus the profile, route decision, review policy decision, latency, and a preprocessing summary.

Flags:

| flag | purpose |
| --- | --- |
| `--manifest` | alternative full manifest (default `data/manifests/manifest.jsonl`) |
| `--subset` | restrict to a subset manifest (the typical case) |
| `--limit N` | process only the first N rows |
| `--dry-run` | skip the Anthropic call — produces profile + route + preprocessing stats only |
| `--force-route …` | bypass the router (Modes B and C) |
| `--mode {B,C,D}` | shorthand: `B` forces `rendered_multimodal`, `C` forces `preprocessed_multimodal`, `D` uses the router |
| `--timestamp` | reuse a specific timestamp (for reruns over the same directory) |

Errors never abort the run — they are logged to `errors.jsonl` and the runner continues. Each document either produces an `OK` row with a full per-document JSON, a `DRY_RUN` row, or an `ERROR` row with the exception class + message.

## 6. Evaluation

```bash
python -m scripts.run_eval --mode D \
    --run-dir data/batch_runs/<timestamp> \
    --gold data/gold_candidates/gold_candidates_prefill.jsonl \
    --provisional
```

Metrics (in `metrics.json`):

| metric | definition |
| --- | --- |
| `field_accuracy` | `sum(field_hits) / sum(field_total)` across all documents. |
| `critical_field_accuracy` | Same, restricted to the 6 critical fields (`supplier_name`, `document_type`, `heat_numbers`, `grades`, `yield_strength_mpa`, `tensile_strength_mpa`). |
| `compliance_decision_accuracy` | Fraction of docs where predicted `is_compliant` equals gold `is_compliant`. |
| `review_rate` | Fraction of OK docs with `needs_review == true`. |
| `stp_rate` | `1 - review_rate` (straight-through processing). |
| `average_latency_ms` / `p95_latency_ms` | Wall-clock latency per document. |
| `extraction_completeness` | Fraction of critical fields where *any* value was produced (independent of correctness). |

Field comparisons normalise strings (casefold + whitespace squash), lists (sort + dedupe), and floats (sorted + 1-unit tolerance). This is intentionally permissive because the gold itself is pipe-delimited reviewer text.

### Experiment-mode comparability

| Mode | command | What it probes |
| --- | --- | --- |
| A | `scripts.run_eval --mode A` | Prints skip reason and exits 0. |
| B | `scripts.run_batch_extraction --mode B` → `scripts.run_eval --mode B` | No routing — every doc runs with `rendered_multimodal`. |
| C | `scripts.run_batch_extraction --mode C` → `scripts.run_eval --mode C` | Always runs the full preprocessed stack. |
| D | `scripts.run_batch_extraction --mode D` → `scripts.run_eval --mode D` | The proposed routed hybrid. |

For a head-to-head comparison, run B, C, and D with the **same subset**, then flatten the results:

```bash
python -m scripts.export_eval_summary
```

`data/eval_outputs/eval_summary.md` contains one row per mode with all aggregate metrics side by side.
