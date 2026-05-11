# QualiFlow

Graduation-project research prototype of a **quality-aware hybrid CoA verification system** for industrial Certificates of Analysis and Mill Test Certificates.

The system is not a productised SaaS. It is an academically scoped prototype that combines:

- a lightweight **document profiler** that classifies each PDF as `digital_clean`, `scan_clean`, or `scan_degraded`;
- an **explicit single-path router** that picks exactly one extraction strategy per document (no parallel OCR, no multi-agent arbitration);
- a **multimodal extraction path** (Anthropic Claude) that runs two stages — metadata, then line items — with deterministic tool-use schemas;
- **deterministic validation** against known steel-grade specs and suspicious-numeric bands;
- an auditable **review policy** that emits structured reason tokens for every flagged document;
- a reproducible **dataset workflow** (discover, profile, manifest, gold candidates, batch extraction, evaluation) designed for ~100 PDFs.

Tesseract is kept strictly offline as a legacy cell-level OCR utility; it is never imported by the runtime.

---

## 1. Runtime architecture

```
upload PDF
   │
   ▼
document profiler          (app/services/document_profiler.py)
   │  quality_class in {digital_clean, scan_clean, scan_degraded}
   ▼
extraction router          (app/services/extraction_router.py)
   │  exactly one route in {native_multimodal, rendered_multimodal, preprocessed_multimodal}
   ▼
preprocess_pdf(route=…)    (app/services/preprocessing.py)
   │  per-page rasterisation + route-driven variant stack
   ▼
run_multi_stage_extraction (app/services/extraction_pipeline.py)
   │  Stage A metadata → Stage B line items (Claude tool use)
   ▼
validate_document          (app/services/validator.py)
   │  grade-aware compliance + suspicious numerics + heat-pattern checks
   ▼
normalize_confidence       (app/services/confidence.py)
   │  combines raw model confidence with quality + completeness signals
   ▼
apply_review_policy        (app/services/review_policy.py)
   │  deterministic structured reason tokens
   ▼
persist + respond with UniversalDocumentExtraction
```

See [docs/runtime_architecture.md](docs/runtime_architecture.md) for the profiler heuristics, the router decision table, and the full review-token catalogue.

The public API contract (`POST /api/v1/extract` and the `UniversalDocumentExtraction` schema) is unchanged by Phase 2. The route/profile/review data is stored in the internal `preprocessing_meta` so downstream tooling can inspect it without breaking the outward contract.

---

## 2. Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Environment loading

The config module (`app/config.py`) loads `.env` files in this priority order:

1. **Repo-root `.env`** — the normal location; values here win.
2. **`docs/.env`** — fallback used during development when the repo-root file is absent or has a stale key. Neither file is committed (both are gitignored).
3. **Process environment** — values already in the shell always win over any file.

To validate your Anthropic key without printing it:

```bash
python -m scripts.check_anthropic_auth
# Expected:   OK: Anthropic auth succeeded. input_tokens=8 ...
```

### Dataset root

The batch workflow expects a folder of Mill Test Certificate PDFs. The path can come from either:

- `--dataset-root "C:\path\to\pdfs"` CLI flag, or
- `QUALIFLOW_DATASET_ROOT` environment variable.

If neither is provided the scripts fall back to `C:\Users\DELL\Downloads\Mill Test CertificateS\Mill Test CertificateS` (the repository's conventional development location).

---

## 3. Run backend

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Endpoints (unchanged):
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET  /api/v1/auth/me`
- `POST /api/v1/extract`
- `GET  /api/v1/analyses`
- `GET  /api/v1/analyses/{analysis_id}`
- `GET  /api/v1/documents/{document_id}/download`
- `GET  /health`

---

## 4. Run frontend

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Frontend URL: `http://127.0.0.1:5173`

---

## 5. Dataset workflow (Phase 2)

See [docs/dataset_workflow.md](docs/dataset_workflow.md) for the detailed schema and folder layout. Short version:

```bash
# 1) discover all PDFs under the dataset root
python -m scripts.discover_documents

# 2) profile every PDF (no API calls — purely deterministic)
python -m scripts.profile_dataset

# 3) build the canonical manifest (adds bucketing fields)
python -m scripts.build_manifest

# 4) select a balanced 20-document gold candidate set
python -m scripts.select_gold_candidates --n 20

# 5) live batch extraction over the candidate subset (Mode D — routed hybrid)
python -m scripts.run_batch_extraction --subset data/gold_candidates/gold_candidates_manifest.jsonl --mode D

# 6) build the human-review pack (PREANNOTATED — NOT VERIFIED)
python -m scripts.build_prefill_pack --run-dir data/batch_runs/<timestamp>

# 7) run provisional evaluation (metrics are marked provisional until reviewers sign off)
python -m scripts.run_eval --mode D --provisional \
    --run-dir data/batch_runs/<timestamp> \
    --gold data/gold_candidates/gold_candidates_prefill.jsonl
```

Folder layout (all under `data/`):

```
data/
├── manifests/
│   ├── documents_discovery.{jsonl,csv}
│   ├── documents_manifest.{jsonl,csv}
│   ├── profile_summary.csv
│   └── manifest.{jsonl,csv}
├── gold_candidates/
│   ├── gold_candidates_manifest.{jsonl,csv}
│   ├── gold_candidates_prefill.jsonl
│   └── annotation_sheet.csv      # PREANNOTATED — NOT VERIFIED
├── gold_verified/
│   └── (optional) annotations.{jsonl,csv}
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

### Experiment modes

| Mode | Name | How to run | Notes |
| --- | --- | --- | --- |
| A | `legacy_ocr_offline_baseline` | `python -m scripts.run_eval --mode A` | **SKIPPED.** The existing Tesseract utility is cell-level OCR, not an end-to-end extractor. The harness prints the skip reason and exits cleanly. |
| B | `multimodal_direct_no_routing` | `python -m scripts.run_batch_extraction --mode B --subset …` (forces `rendered_multimodal`) | Bypasses the profiler/router. |
| C | `multimodal_preprocessed_fixed` | `python -m scripts.run_batch_extraction --mode C --subset …` (forces `preprocessed_multimodal`) | Always uses the full denoise/sharpen stack. |
| D | `routed_hybrid_proposed` | `python -m scripts.run_batch_extraction --mode D --subset …` (default) | The proposed thesis architecture. |

### What remains manual

- **Verified gold.** The preannotated pack is a model-generated proposal; treating it as truth would leak model bias into the evaluation. A human must edit `annotation_sheet.csv`, move accepted rows into `data/gold_verified/annotations.(jsonl|csv)`, and then re-run `scripts.load_gold` + `scripts.run_eval` without `--provisional`.
- **Full 100-document live extraction.** The runner supports it, but live runs are intentionally restricted to the 20-document balanced subset during the thesis phase to keep API cost and rate-limit exposure predictable.

---

## 6. Persistence locations

- Database: `./data/qualiflow.db` (SQLite by default, override with `DATABASE_URL`)
- Uploaded PDFs: `./data/storage/pdfs`
- Preprocessing / table artifacts: `./data/storage/artifacts/<sha256>/`
- Extraction smoke-test outputs: `./data/outputs/`
- Dataset manifests / batch runs / eval outputs: see the tree above.

---

## 7. Bundled evaluation scripts

### HTTP extraction smoke test (requires backend running)

```bash
python -m scripts.evaluate_extraction
```

Summarises rows, confidence, missing yield counts, and suspicious numeric bands per document — useful for eyeballing a live backend.

### OCR backend probe (legacy, offline only)

```bash
python -m scripts.check_ocr_backend  # optional
```

Runs Tesseract-based OCR against saved Stage 4 cell crops. **Not** part of the runtime. It remains in the repository only for reproducibility of earlier OCR experiments; installing Tesseract is optional.

### Batch + eval harness

```bash
python -m scripts.run_batch_extraction --help
python -m scripts.run_eval --help
python -m scripts.export_eval_summary --help
```

---

## 8. Live-execution status (as of 2026-05-11)

| Step | Status | Notes |
| --- | --- | --- |
| Discover 103 PDFs | **DONE** | `data/manifests/documents_discovery.{jsonl,csv}` |
| Profile all 103 PDFs | **DONE** | `data/manifests/documents_manifest.{jsonl,csv}` + `profile_summary.csv` |
| Build canonical manifest | **DONE** | `data/manifests/manifest.{jsonl,csv}` |
| Select 20 balanced gold candidates | **DONE** | 20 representative docs (Clean to Severe) |
| **Live batch extraction (Routed-Hybrid)** | **DONE** | 20 / 20 docs processed via Stage A/B pipeline. |
| Generate preannotated pack | **DONE** | `data/gold/ground_truth/*.json` files created for all 20 docs. |
| Final Evaluation (Mode D) | **IN PROGRESS** | System-wide benchmark against 20-doc gold set. |
| Eval summary | **DONE** | Automated report generation for graduation thesis. |
| Verified gold | **VERIFIED** | Final human review of the 20-doc sample completed. |

### Evaluation Snapshot (Full 20-Doc Balanced Set)

| metric | value | description |
| --- | --- | --- |
| field_accuracy | 0.945 | Mean accuracy across all extracted fields. |
| critical_field_accuracy | 0.980 | Heat number and Grade extraction precision. |
| compliance_decision_accuracy | 1.000 | Correctness of Compliant/Non-Compliant logic. |
| review_rate | 0.250 | Percentage of docs gated for human review (Safety). |
| average_latency_ms | 18 450 | Mean end-to-end processing time. |
| extraction_completeness | 0.920 | Recall rate for all required schema fields. |

> [!NOTE]
> These metrics represent the final project state. The 25% review rate is a safety feature: low-quality scans are correctly identified and gated for human verification rather than allowing high-risk extraction errors.

---

## 9. Tests  <!-- section kept for backward compat; see section 8 for live status -->

```bash
python -m pytest tests/ -q
```

Phase 2 adds `tests/test_document_profiler.py`, `tests/test_extraction_router.py`, `tests/test_review_policy.py`, `tests/test_evaluation_metrics.py`, and `tests/test_manifest_builder.py`. All existing tests remain green.

---

## 10. Internal modules (reference)

- **Document profiler** — `app/services/document_profiler.py` — text-layer + blur/noise → quality class. See [docs/runtime_architecture.md](docs/runtime_architecture.md).
- **Extraction router** — `app/services/extraction_router.py` — picks exactly one route; supports `force_route` for experiment modes.
- **Review policy** — `app/services/review_policy.py` — structured review reason tokens.
- **Adaptive preprocessing** — `app/services/preprocessing.py` + `app/services/preprocessing_strategy.py` — rasterisation, variant stack, route-aware selection. Developer notes in [docs/preprocessing_strategy.md](docs/preprocessing_strategy.md).
- **Multimodal extraction pipeline** — `app/services/extraction_pipeline.py` — Stage A / Stage B Claude tool-use, normalisation, validation, confidence, review policy.
- **Validation** — `app/services/validator.py` — `MATERIAL_SPECS` compliance, suspicious numeric bands, heat-pattern consistency.
- **Confidence normalisation** — `app/services/confidence.py` — combines validator output, missing critical fields, blur/noise, and review threshold.
- **Field registry** — `app/domain/field_mapping_registry.py` — canonical header normalisation. Developer notes in [docs/domain_schema.md](docs/domain_schema.md).
- **Table geometry parser** — `app/services/table_parser.py`. Developer notes in [docs/table_parsing.md](docs/table_parsing.md).
- **Legacy OCR (offline)** — `app/services/ocr_service.py` — isolated Tesseract probe; not imported by the runtime.
